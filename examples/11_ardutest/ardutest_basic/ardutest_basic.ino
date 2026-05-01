#include <ArduTest.h>

TEST_CASE(test_true_passes)
{
  ArduTest.log("running test_true_passes");
  ASSERT_TRUE(true);
}

TEST_CASE(test_numbers_match)
{
  ASSERT_EQ(42, 42);
}

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
