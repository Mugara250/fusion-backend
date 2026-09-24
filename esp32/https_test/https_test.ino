// Minimal test: can this board reach the hosted backend at all?
// Upload, open Serial Monitor at 115200, read the result. Nothing else runs.

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

const char* WIFI_NAME     = "Nico";
const char* WIFI_PASSWORD = "PUT-YOUR-WORKING-PASSWORD";
const char* HOST          = "fusion-backend-q7qa.onrender.com";

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.printf("\nESP32 core %s, free memory %u\n", ESP.getSdkVersion(), ESP.getFreeHeap());

  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.println(" connected, IP " + WiFi.localIP().toString());

  IPAddress ip;
  Serial.print("DNS lookup: ");
  Serial.println(WiFi.hostByName(HOST, ip) ? ip.toString() : String("FAILED (no internet on hotspot)"));

  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;
  http.begin(client, String("https://") + HOST + "/health");
  int code = http.GET();
  Serial.printf("GET /health -> %d %s\n", code, code > 0 ? http.getString().c_str()
                                                          : http.errorToString(code).c_str());
  if (code < 0) {
    char err[120];
    client.lastError(err, sizeof(err));
    Serial.printf("TLS detail: %s\n", err);
  }
  http.end();
}

void loop() {}
