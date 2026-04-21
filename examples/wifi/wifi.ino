#include <WiFi.h>

constexpr unsigned long WIFI_TIMEOUT_MS = 30000;

void setup()
{
  Serial.begin(115200);
  delay(1000);

  if (String(WIFI_SSID).isEmpty())
  {
    Serial.println("WIFI_ERROR missing_ssid");
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_TIMEOUT_MS)
  {
    delay(250);
  }

  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.printf("WIFI_ERROR connect_failed %d\n", static_cast<int>(WiFi.status()));
    return;
  }

  Serial.print("WIFI_OK ");
  Serial.println(WiFi.localIP());
}

void loop()
{
  delay(1000);
}
