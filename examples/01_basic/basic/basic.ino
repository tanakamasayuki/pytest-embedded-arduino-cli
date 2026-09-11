void setup()
{
  Serial.begin(115200);
}

void loop()
{
  if (Serial.available() == 0)
  {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line == "ping")
  {
    Serial.println("PONG");
  }
}
