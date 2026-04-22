#include <unity.h>

int add(int left, int right)
{
  return left + right;
}

void test_add_positive_numbers()
{
  TEST_ASSERT_EQUAL(3, add(1, 2));
}

void test_add_negative_numbers()
{
  TEST_ASSERT_EQUAL(-1, add(2, -3));
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
