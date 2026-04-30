void setup() {
  Serial.begin(115200);
  delay(100);

#ifdef PYTEST_BUILD
  Serial.println("PYTEST_BUILD enabled");
#else
  Serial.println("PYTEST_BUILD disabled");
#endif

#ifdef ENABLE_TEST_HOOKS
  Serial.println("TEST_HOOKS enabled");
#else
  Serial.println("TEST_HOOKS disabled");
#endif

#ifdef DISABLED_FLAG
  Serial.println("DISABLED_FLAG enabled");
#else
  Serial.println("DISABLED_FLAG disabled");
#endif
}

void loop() {}
