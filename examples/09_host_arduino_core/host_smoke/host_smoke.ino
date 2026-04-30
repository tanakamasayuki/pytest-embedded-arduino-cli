void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("HOST_SMOKE_READY");
}

void loop() {
  static char payload[64];
  static size_t payload_len = 0;

  while (Serial.available()) {
    int c = Serial.read();
    if (c < 0) {
      break;
    }

    if (c == '\r') {
      continue;
    }

    if (c == '\n') {
      payload[payload_len] = '\0';
      Serial.print("HOST_SMOKE_ECHO ");
      Serial.println(payload);
      payload_len = 0;
      continue;
    }

    if (payload_len + 1 < sizeof(payload)) {
      payload[payload_len++] = static_cast<char>(c);
    }
  }

  delay(10);
}
