String readLineFromSerial() {
  String line = "";

  while (true) {
    while (Serial.available() == 0) {
      delay(10);
    }

    char ch = static_cast<char>(Serial.read());
    if (ch == '\r') {
      continue;
    }
    if (ch == '\n') {
      return line;
    }
    line += ch;
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("READY");
  String received = readLineFromSerial();
  Serial.print("RECEIVED ");
  Serial.println(received);
  Serial.println("OK");
}

void loop() {}
