#include <Preferences.h>

Preferences preferences;

void setup()
{
  Serial.begin(115200);
  delay(1000);

  preferences.begin("pytest-demo", false);
  unsigned int bootCount = preferences.getUInt("boot_count", 0);
  bootCount += 1;
  preferences.putUInt("boot_count", bootCount);
  preferences.end();

  Serial.print("BOOT_COUNT ");
  Serial.println(bootCount);
}

void loop()
{
}
