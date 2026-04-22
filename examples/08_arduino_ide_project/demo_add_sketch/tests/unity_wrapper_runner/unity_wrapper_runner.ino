#include <Arduino.h>
#include <unity.h>
#include <add_test.h>

AddTest add_test;

void setUp(void)
{
}

void tearDown(void)
{
}

void test_add_returns_sum_for_positive_integers(void)
{
  TEST_ASSERT_EQUAL_INT(5, add_test.add(2, 3));
}

void test_add_returns_zero_for_zero_inputs(void)
{
  TEST_ASSERT_EQUAL_INT(0, add_test.add(0, 0));
}

void test_add_handles_negative_values(void)
{
  TEST_ASSERT_EQUAL_INT(-1, add_test.add(2, -3));
}

void setup()
{
  Serial.begin(115200);
  delay(1000);

  UNITY_BEGIN();
  RUN_TEST(test_add_returns_sum_for_positive_integers);
  RUN_TEST(test_add_returns_zero_for_zero_inputs);
  RUN_TEST(test_add_handles_negative_values);
  UNITY_END();
}

void loop()
{
  delay(1000);
}
