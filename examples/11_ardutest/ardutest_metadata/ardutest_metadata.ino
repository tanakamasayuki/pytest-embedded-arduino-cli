#include <ArduTest.h>

TEST_CASE(test_sample_rate)
{
  int sampleRate = ArduTest.configInt("sample_rate");
  ArduTest.log("received sample_rate");
  ArduTest.reportMetric("sample_rate", sampleRate);
  ArduTest.attachText("sample_rate.txt", ArduTest.config("sample_rate"));
  ASSERT_EQ(1000, sampleRate);
}
ARDUTEST_REQUIRE(test_sample_rate, "measurement.current");
ARDUTEST_REQUIRE_CONFIG(test_sample_rate, "sample_rate");

void setup()
{
  Serial.begin(115200);
  delay(1000);
  ArduTest.begin();
}

void loop()
{
  ArduTest.poll();
}
