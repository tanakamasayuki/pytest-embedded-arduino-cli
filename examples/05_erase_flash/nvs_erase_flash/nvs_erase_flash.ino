#ifdef ARDUINO_ARCH_ESP32
#include <Preferences.h>
#endif

#ifdef ARDUINO_ARCH_ESP32
Preferences preferences;
#endif

void setup() {
  Serial.begin(115200);
  delay(1000);

#ifdef ARDUINO_ARCH_ESP32
  preferences.begin("pytest-demo", false);
  unsigned int bootCount = preferences.getUInt("boot_count", 0);
  bootCount += 1;
  preferences.putUInt("boot_count", bootCount);
  preferences.end();

  Serial.print("BOOT_COUNT ");
  Serial.println(bootCount);
#else
  Serial.println("UNO_UNSUPPORTED");
#endif
}

void loop() {}
