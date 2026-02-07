from sc_engine import Engine

_engine = Engine()

def decode_file(path, name):
    return _engine.decode_file(path, name)

def encode_file(path):
    return _engine.encode_file(path)
