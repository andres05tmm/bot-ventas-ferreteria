# FerreVoz — build y prueba

App Android del asistente de voz de FerreBot. Fase 2: una vuelta manual de voz.

## Requisitos
- **Android Studio** (Koala 2024.1.1 o más nuevo).
- **JDK 17** (Android Studio ya lo trae embebido).
- Un celular Android **8.0+ (API 26)** con depuración USB, o un emulador.
- El backend de FerreBot corriendo y accesible por **https** (tu URL de Railway).

## Abrir y compilar
1. En Android Studio: **Open** → seleccioná la carpeta `android-voz/`.
   - Al abrir, Android Studio descarga Gradle 8.9 (definido en `gradle/wrapper/gradle-wrapper.properties`)
     y sincroniza. La primera sincronización baja dependencias (unos minutos).
   - Si te pide crear `local.properties`, Android Studio la genera con la ruta del SDK
     (no se commitea: está en `.gitignore`).
2. Conectá el celular (o iniciá un emulador) y dale **Run ▶** (configuración `app`).

### Build de APK para sideload (vendedores)
- Menú **Build → Build App Bundle(s) / APK(s) → Build APK(s)**, o por CLI dentro de `android-voz/`:
  ```
  ./gradlew assembleDebug
  ```
  (En Windows: `gradlew.bat assembleDebug`. Si no existe el wrapper aún, abrí una vez en
  Android Studio para que lo genere, o corré `gradle wrapper` con un Gradle de sistema.)
- El APK queda en `app/build/outputs/apk/debug/app-debug.apk`. Se instala en el celular
  habilitando "instalar apps de origen desconocido".

## Primer uso
1. Abrí la app. Se muestra el diálogo de **Ajustes** (porque no hay URL configurada).
2. Pegá la **URL del servidor** (ej. `https://tu-app.up.railway.app`) y tu **nombre de vendedor**.
   Guardá.
3. Tocá el **botón de micrófono**. La primera vez Android pide permiso de micrófono → Permitir.
4. Tocá para hablar, decí p. ej. *"dos bultos de cemento"*, y tocá de nuevo para enviar.
   La app transcribe, consulta al cerebro y **te responde hablando**.

## Notas
- La IA, el catálogo y el registro de ventas viven en el **backend**; esta app solo
  consume los endpoints `/chat/transcribir` y `/chat/stream` (canal `"voz"`).
- El pago por voz, el loop continuo y el botón del audífono llegan en fases siguientes
  (ver `../.planning/voz-asistente/PLAN.md`).
