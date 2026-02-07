import io
import os
import struct
import json
import shutil
import zipfile
import subprocess
import zstandard as zstd
from PIL import Image
import texture2ddecoder
from sc_compression import Decompressor, Compressor, Signatures

GL_MAP = {
    0x93B0: ("ASTC_4x4", 4, 4), 0x93B1: ("ASTC_5x4", 5, 4), 0x93B2: ("ASTC_5x5", 5, 5),
    0x93B3: ("ASTC_6x5", 6, 5), 0x93B4: ("ASTC_6x6", 6, 6), 0x93B5: ("ASTC_8x5", 8, 5),
    0x93B6: ("ASTC_8x6", 8, 6), 0x93B7: ("ASTC_8x8", 8, 8), 0x93B8: ("ASTC_10x5", 10, 5),
    0x93B9: ("ASTC_10x6", 10, 6), 0x93BA: ("ASTC_10x8", 10, 8), 0x93BB: ("ASTC_10x10", 10, 10),
    0x93BC: ("ASTC_12x10", 12, 10), 0x93BD: ("ASTC_12x12", 12, 12),
    0x9278: ("ETC2", 0, 0), 0x8D64: ("ETC1", 0, 0),
    0x8058: ("RGBA8", 0, 0), 0x8051: ("RGB8", 0, 0), 0x8036: ("LUMINANCE", 0, 0)
}

class Engine:
    def __init__(self):
        pass

    def decode_file(self, file_path, filename, progress_callback=None):
        base_dir = os.path.dirname(file_path)
        clean_name = filename.rsplit('.', 1)[0]
        work_dir = os.path.join(base_dir, clean_name + "_extracted")
        if os.path.exists(work_dir): shutil.rmtree(work_dir)
        os.makedirs(work_dir)

        if progress_callback: progress_callback("Reading file...", 5)
        with open(file_path, "rb") as f: raw_data = f.read()

        decompressed_data = raw_data
        sig = "RAW"
        zstd_sig = b'\x28\xb5\x2f\xfd'
        zstd_pos = raw_data.find(zstd_sig)
        header_data = b""

        zstd_ok = False
        if zstd_pos != -1:
            if progress_callback: progress_callback("Decompressing ZSTD...", 10)
            header_data = raw_data[:zstd_pos]
            dctx = zstd.ZstdDecompressor()
            try:
                decompressed_data = dctx.decompress(raw_data[zstd_pos:])
                sig = "SCTX_ZSTD"
                zstd_ok = True
            except zstd.ZstdError:
                try:
                    with dctx.stream_reader(io.BytesIO(raw_data[zstd_pos:])) as reader:
                        decompressed_data = reader.read()
                    sig = "SCTX_ZSTD"
                    zstd_ok = True
                except Exception:
                    header_data = b""
        if not zstd_ok:
            try:
                if progress_callback: progress_callback("Decompressing LZMA...", 10)
                decompressed_data = Decompressor().decompress(raw_data)
                sig = "SC_LZMA"
            except: pass

        KTX_MAGIC = b'\xABKTX 11\xBB\r\n\x1A\n'
        offsets = []
        last = 0
        while True:
            p = decompressed_data.find(KTX_MAGIC, last)
            if p == -1: break
            offsets.append(p)
            last = p + 12

        layout = {
            "filename": filename, "signature": sig, "has_header": len(header_data) > 0, "textures": []
        }

        with open(os.path.join(work_dir, "base_dump.bin"), "wb") as f: f.write(decompressed_data)
        if len(header_data) > 0:
            with open(os.path.join(work_dir, "header.bin"), "wb") as f: f.write(header_data)

        if not offsets and sig in {"SCTX_ZSTD", "RAW"}:
            if progress_callback: progress_callback("Scanning RAW textures...", 20)
            configs = [
                (1024, 1024, 8, 8, "ASTC_8x8_RAW"), (1024, 1024, 4, 4, "ASTC_4x4_RAW"),
                (512, 512, 8, 8, "ASTC_8x8_RAW"), (512, 512, 4, 4, "ASTC_4x4_RAW"),
                (1024, 1024, 6, 6, "ASTC_6x6_RAW"),
            ]
            for w, h, bw, bh, fmt_name in configs:
                req_size = (w * h * 16) // (bw * bh)
                if len(decompressed_data) >= req_size:
                    try:
                        dec = texture2ddecoder.decode_astc(decompressed_data[:req_size], w, h, bw, bh)
                        img = Image.frombytes('RGBA', (w, h), dec, 'raw', 'BGRA')
                        tex_name = f"texture_0_{w}x{h}.png"
                        img.save(os.path.join(work_dir, tex_name))
                        layout["textures"].append({
                            "index": 0, "name": tex_name, "offset_start": 0, "offset_end": req_size,
                            "width": w, "height": h, "format": fmt_name
                        })
                        break
                    except: pass
        else:
            offsets.append(len(decompressed_data))
            total_tex = len(offsets) - 1
            for i in range(total_tex):
                percent = 20 + int((i / total_tex) * 70)
                if progress_callback: progress_callback(f"Decoding texture {i+1}/{total_tex}...", percent)

                s, e = offsets[i], offsets[i+1]
                chunk = decompressed_data[s:e]
                try:
                    gl = struct.unpack('<I', chunk[28:32])[0]
                    w = struct.unpack('<I', chunk[36:40])[0]
                    h = struct.unpack('<I', chunk[40:44])[0]
                    kv = struct.unpack('<I', chunk[60:64])[0]
                    tex_data = chunk[64+kv+4:]

                    fmt_info = GL_MAP.get(gl)
                    if not fmt_info: continue

                    fmt_name, bw, bh = fmt_info
                    img = None

                    if "ASTC" in fmt_name:
                        dec = texture2ddecoder.decode_astc(tex_data, w, h, bw, bh)
                        img = Image.frombytes('RGBA', (w, h), dec, 'raw', 'BGRA')
                    elif "ETC2" in fmt_name:
                        dec = texture2ddecoder.decode_etc2a8(tex_data, w, h)
                        img = Image.frombytes('RGBA', (w, h), dec, 'raw', 'BGRA')
                    elif "ETC1" in fmt_name:
                        dec = texture2ddecoder.decode_etc1(tex_data, w, h)
                        img = Image.frombytes('RGBA', (w, h), dec, 'raw', 'BGRA')
                    elif "RGBA8" in fmt_name:
                        img = Image.frombytes('RGBA', (w, h), tex_data, 'raw', 'RGBA')

                    nm = f"texture_{i}.png"
                    if img: img.save(os.path.join(work_dir, nm))

                    layout["textures"].append({
                        "index": i, "name": nm, "offset_start": s, "offset_end": e,
                        "width": w, "height": h, "format": fmt_name
                    })
                except: pass

        if progress_callback: progress_callback("Creating ZIP...", 95)
        with open(os.path.join(work_dir, "layout.json"), "w") as f: json.dump(layout, f, indent=4)
        zip_path = os.path.join(base_dir, f"{filename}.zip")
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for root, _, files in os.walk(work_dir):
                for file in files: zf.write(os.path.join(root, file), file)

        if progress_callback: progress_callback("Done!", 100)
        return zip_path

    def encode_file(self, zip_path, progress_callback=None):
        base_dir = os.path.dirname(zip_path)
        work_dir = os.path.join(base_dir, "encode_work")
        if os.path.exists(work_dir): shutil.rmtree(work_dir)
        os.makedirs(work_dir)

        if progress_callback: progress_callback("Extracting ZIP...", 5)
        with zipfile.ZipFile(zip_path, 'r') as zf: zf.extractall(work_dir)
        with open(os.path.join(work_dir, "layout.json"), "r") as f: layout = json.load(f)

        base_path = os.path.join(work_dir, "base_dump.bin")
        if not os.path.exists(base_path): return None
        with open(base_path, "rb") as f: base_data = bytearray(f.read())

        astc_bin = "astcenc"
        total_tex = len(layout["textures"])

        for i, tex in enumerate(layout["textures"]):
            percent = 10 + int((i / total_tex) * 80)
            if progress_callback: progress_callback(f"Compressing {tex['name']} ({i+1}/{total_tex})...", percent)

            png_path = os.path.join(work_dir, tex["name"])
            if not os.path.exists(png_path): continue

            if "ASTC" in tex["format"]:
                astc_out = os.path.join(work_dir, "temp.astc")
                blk = "8x8"
                if "_" in tex["format"]:
                    parts = tex["format"].split("_")
                    if len(parts) > 1 and "x" in parts[1]: blk = parts[1]

                try:
                    subprocess.run([astc_bin, "-cl", png_path, astc_out, blk, "-medium"], stdout=subprocess.DEVNULL, check=True)
                    if os.path.exists(astc_out):
                        with open(astc_out, "rb") as f: raw_astc = f.read()[16:]
                        if "RAW" in tex["format"]:
                            if len(layout["textures"]) == 1: base_data = raw_astc
                        else:
                            s = tex["offset_start"]
                            try:
                                kv_len = struct.unpack('<I', base_data[s+60:s+64])[0]
                                data_start = s + 64 + kv_len + 4
                                base_data[data_start : data_start + len(raw_astc)] = raw_astc
                            except: pass
                except: pass

        if progress_callback: progress_callback("Finalizing...", 95)
        final_data = b""
        if layout["signature"] == "SCTX_ZSTD":
            cctx = zstd.ZstdCompressor(level=3)
            compressed = cctx.compress(base_data)
            header_path = os.path.join(work_dir, "header.bin")
            if os.path.exists(header_path):
                with open(header_path, "rb") as f: final_data = f.read() + compressed
            else: final_data = compressed
        else:
            final_data = base_data

        out_name = "encoded_" + layout["filename"]
        out_path = os.path.join(base_dir, out_name)
        with open(out_path, "wb") as f: f.write(final_data)

        if progress_callback: progress_callback("Done!", 100)
        return out_path
