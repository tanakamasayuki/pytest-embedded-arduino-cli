void setup() {
  Serial.begin(115200);
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command == "ready?") {
      Serial.println("PEER_HOST_ECHO_READY");
    }
  }

  delay(10);
}
