# SC Tools Android

## Сборка
```bash
cd android
./gradlew assembleDebug
```

## Подписание релизного APK
1. Создайте keystore:
   ```bash
   keytool -genkeypair -v -keystore sc-tools.keystore -alias sctools -keyalg RSA -keysize 2048 -validity 10000
   ```
2. Создайте `keystore.properties` рядом с `settings.gradle`:
   ```properties
   storeFile=sc-tools.keystore
   storePassword=your_store_password
   keyAlias=sctools
   keyPassword=your_key_password
   ```
3. Соберите релиз:
   ```bash
   ./gradlew assembleRelease
   ```

Если `keystore.properties` отсутствует, релизный билд соберется без подписи.
