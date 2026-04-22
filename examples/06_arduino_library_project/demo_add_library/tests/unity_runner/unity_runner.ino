#include <DemoAdd.h>
#include <unity.h>

DemoAdd demo;

void test_add_positive_numbers()
{
  TEST_ASSERT_EQUAL(3, demo.add(1, 2));
}

void test_add_negative_numbers()
{
  TEST_ASSERT_EQUAL(-1, demo.add(2, -3));
}

void setup()
{
  Serial.begin(115200);
  delay(1000);

  UNITY_BEGIN();
  RUN_TEST(test_add_positive_numbers);
  RUN_TEST(test_add_negative_numbers);
  UNITY_END();
}

void loop()
{
}
