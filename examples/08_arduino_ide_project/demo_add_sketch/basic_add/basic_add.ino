#include <add_test.h>

AddTest add_test;

void setup()
{
  Serial.begin(115200);
  delay(1000);
}

void loop()
{
  const int left = 2;
  const int right = 3;
  const int result = add_test.add(left, right);

  Serial.print("ADD_RESULT ");
  Serial.println(result);
  delay(5000);
}
