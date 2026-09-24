// ============================================================================
//  FUSION - THE BODY
//  Joins WiFi, FINDS THE LAPTOP BY ITSELF, asks the backend for the finger
//  count 5 times a second, and lights that many LEDs. Ticks the buzzer when a
//  light comes on. Flashes all LEDs when SOS is on (hold the rock sign for 2 s).
//
//  No laptop IP to type: the board searches the network for the backend's
//  /health answer and remembers the address. If the laptop's IP changes, it
//  searches again automatically.
//  Manual override: type an IP (e.g. 172.20.10.2) in the Serial Monitor.
//  Hosted backend (Render etc.): put its URL in BACKEND_URL and the search is skipped.
//
//  Board:          Tools -> Board -> esp32 -> "ESP32 Dev Module"
//  Serial Monitor: 115200 baud, "New Line"
// ============================================================================

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Preferences.h>

// ------------------------- CHANGE THESE LINES -------------------------------
const char* WIFI_NAME     = "Nico";     // exactly as your phone shows it
const char* WIFI_PASSWORD = "isimbii";  // capitals matter, must be 8+ characters

// Hosted backend: e.g. "https://fusion-backend-xxxx.onrender.com/fingers"
// Leave "" to search the local WiFi for the laptop instead.
const char* BACKEND_URL   = "https://fusion-backend-q7qa.onrender.com/fingers";
// ----------------------------------------------------------------------------

const int BACKEND_PORT = 8000;

// Your wiring. 1 finger lights the first LED in this list, 2 fingers the
// first two, and so on. Reorder the list to change the lighting order.
const int LED_PINS[5]    = {14, 4, 5, 13, 2};
const char* LED_NAMES[5] = {"red", "green", "yellow 1", "yellow 2", "blue"};
const int BUZZER_PIN     = 18;

const int POLL_MS          = 200;  // ask 5 times a second
const int ERRORS_UNTIL_OFF = 5;    // after ~1 s of failures: go dark and search again

WiFiClientSecure secureClient;  // for https:// URLs (hosted backend)
Preferences prefs;          // flash storage: remembers the backend IP across reboots
IPAddress backendIp;        // 0.0.0.0 until found
String backendUrl;

int shownCount   = -1;
int errorsInARow = 0;

// ---------------------------------------------------------------------------

void setAll(bool on) {
  for (int i = 0; i < 5; i++) digitalWrite(LED_PINS[i], on ? HIGH : LOW);
}

void showFingers(int count) {
  for (int i = 0; i < 5; i++) digitalWrite(LED_PINS[i], i < count ? HIGH : LOW);
}

void tick() {
  tone(BUZZER_PIN, 2000, 40);  // works for both active and passive buzzers
}

// Lights each LED once at power-up so you can check the wiring.
void selfTest() {
  Serial.println("Self test: each LED should light in turn...");
  for (int i = 0; i < 5; i++) {
    Serial.printf("  pin %2d  %s\n", LED_PINS[i], LED_NAMES[i]);
    digitalWrite(LED_PINS[i], HIGH);
    tick();
    delay(250);
    digitalWrite(LED_PINS[i], LOW);
  }
}

// ----------------------------- WIFI ----------------------------------------

// Lists the networks the board can see, so you know if yours is visible.
void scanNetworks() {
  Serial.println("Networks this board can see (2.4 GHz only):");
  int n = WiFi.scanNetworks();
  bool found = false;
  for (int i = 0; i < n; i++) {
    Serial.printf("  \"%s\"  signal %d\n", WiFi.SSID(i).c_str(), WiFi.RSSI(i));
    if (WiFi.SSID(i) == WIFI_NAME) found = true;
  }
  if (n <= 0) Serial.println("  (none)");
  Serial.println(found ? "-> Your network IS visible."
                       : "-> Your network is NOT visible: set the hotspot to 2.4 GHz "
                         "(iPhone: Maximize Compatibility).");
  WiFi.scanDelete();
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  if (strlen(BACKEND_URL) == 0) WiFi.setTxPower(WIFI_POWER_8_5dBm);  // gentler on weak USB power

  if (strlen(WIFI_PASSWORD) > 0 && strlen(WIFI_PASSWORD) < 8) {
    Serial.printf("WARNING: password \"%s\" is %d characters. WiFi passwords are at "
                  "least 8, so it is probably mistyped.\n",
                  WIFI_PASSWORD, strlen(WIFI_PASSWORD));
  }

  Serial.printf("Connecting to WiFi \"%s\"", WIFI_NAME);
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);

  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
    // Blink the first LED while waiting so you can see it without a laptop.
    digitalWrite(LED_PINS[0], !digitalRead(LED_PINS[0]));

    if (millis() - started > 20000) {
      wl_status_t s = WiFi.status();
      Serial.printf("\nStill not connected after 20 s. Status %d: ", s);
      if (s == WL_NO_SSID_AVAIL)
        Serial.println("network NOT FOUND -> it is 5 GHz only, hidden, or the name is wrong.");
      else if (s == WL_CONNECT_FAILED || s == WL_DISCONNECTED)
        Serial.println("network found but REFUSED -> wrong password, or WPA3-only security.");
      else
        Serial.println("check name/password and that the hotspot is on 2.4 GHz.");

      WiFi.disconnect();
      scanNetworks();
      Serial.print("Retrying");
      WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
      started = millis();
    }
  }
  digitalWrite(LED_PINS[0], LOW);

  Serial.println();
  Serial.print("Connected! Board IP: ");
  Serial.println(WiFi.localIP());
}

// ------------------------ FINDING THE BACKEND ------------------------------

void useBackend(IPAddress ip) {
  backendIp  = ip;
  backendUrl = "http://" + ip.toString() + ":" + BACKEND_PORT + "/fingers";
  prefs.putString("ip", ip.toString());
  Serial.print("Using backend: ");
  Serial.println(backendUrl);
}

// True if `ip` answers GET /health with "fusion-backend".
bool isBackend(IPAddress ip) {
  WiFiClient client;
  if (!client.connect(ip, BACKEND_PORT, 200)) return false;  // 200 ms to answer

  client.print("GET /health HTTP/1.0\r\nHost: " + ip.toString() + "\r\n\r\n");
  String reply;
  unsigned long started = millis();
  while (millis() - started < 800 && (client.connected() || client.available())) {
    while (client.available()) reply += (char)client.read();
    if (reply.indexOf("fusion-backend") >= 0) break;
    delay(5);
  }
  client.stop();
  return reply.indexOf("fusion-backend") >= 0;
}

// Tries the remembered IP first, then every address on this network.
// Blinks the green LED while searching.
void findBackend() {
  String saved = prefs.getString("ip", "");
  IPAddress ip;
  if (saved.length() && ip.fromString(saved)) {
    Serial.printf("Trying last known backend %s ... ", saved.c_str());
    if (isBackend(ip)) {
      Serial.println("found.");
      useBackend(ip);
      return;
    }
    Serial.println("not there.");
  }

  IPAddress me   = WiFi.localIP();
  IPAddress mask = WiFi.subnetMask();
  uint32_t net   = (uint32_t)me & (uint32_t)mask;  // stored little-endian
  uint32_t hostBits = ~(uint32_t)mask;
  // Byte-swap to count hosts; cap the search at a /24 (254 addresses).
  uint32_t hosts = __builtin_bswap32(hostBits);
  if (hosts > 255) hosts = 255;

  while (true) {
    Serial.printf("Searching %s/%d for the backend on port %d",
                  me.toString().c_str(), 32 - __builtin_popcount(hostBits), BACKEND_PORT);
    for (uint32_t h = 1; h < hosts; h++) {
      IPAddress candidate(net | __builtin_bswap32(h));
      if (candidate == me) continue;
      digitalWrite(LED_PINS[1], h % 2);  // green blinks while searching
      Serial.print(".");
      if (isBackend(candidate)) {
        digitalWrite(LED_PINS[1], LOW);
        Serial.println(" found!");
        useBackend(candidate);
        return;
      }
      if (Serial.available()) { digitalWrite(LED_PINS[1], LOW); return; }  // manual IP typed
    }
    digitalWrite(LED_PINS[1], LOW);
    Serial.println("\nBackend not found. Is uvicorn running with --host 0.0.0.0, is the laptop");
    Serial.println("on this same WiFi, and is port 8000 allowed? Searching again in 3 s.");
    Serial.println("(Or type the laptop's IP here and press Enter.)");
    delay(3000);
    if (WiFi.status() != WL_CONNECTED || Serial.available()) return;
  }
}

// Type an IP like 172.20.10.2 in the Serial Monitor to set it by hand.
void readSerialCommand() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  IPAddress ip;
  if (ip.fromString(line)) {
    Serial.printf("Manual backend IP: %s\n", line.c_str());
    useBackend(ip);
    errorsInARow = 0;
  } else if (line.length()) {
    Serial.println("Type an IP address like 172.20.10.2");
  }
}

// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(50);
  delay(500);
  Serial.println("\n=== FUSION BODY ===");

  for (int i = 0; i < 5; i++) pinMode(LED_PINS[i], OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  setAll(false);
  prefs.begin("fusion", false);

  selfTest();
  connectWiFi();

  if (strlen(BACKEND_URL) > 0) {
    backendUrl = BACKEND_URL;
    secureClient.setInsecure();  // accept the host's certificate without pinning it
    Serial.print("Using hosted backend: ");
    Serial.println(backendUrl);
    if (!backendUrl.endsWith("/fingers")) Serial.println("WARNING: URL should end with /fingers");
  } else {
    findBackend();
  }
}

bool hosted() { return strlen(BACKEND_URL) > 0; }

// When the hosted backend can't be reached, test each step separately and say which fails.
void diagnoseHosted() {
  String host = backendUrl.substring(backendUrl.indexOf("://") + 3);
  host = host.substring(0, host.indexOf('/'));
  Serial.println("---- diagnosing connection to " + host + " ----");

  IPAddress ip;
  if (!WiFi.hostByName(host.c_str(), ip)) {
    Serial.println("1. Name lookup (DNS): FAILED -> the hotspot gives no internet/DNS.");
    Serial.println("   Turn ON mobile data on the phone sharing the hotspot.");
    return;
  }
  Serial.println("1. Name lookup (DNS): ok -> " + ip.toString());

  WiFiClient plain;
  if (!plain.connect(host.c_str(), 80, 5000)) {
    Serial.println("2. Internet (port 80): FAILED -> hotspot has no working internet.");
    return;
  }
  plain.stop();
  Serial.println("2. Internet (port 80): ok");

  WiFiClientSecure probe;
  probe.setInsecure();
  probe.setHandshakeTimeout(30);
  if (!probe.connect(host.c_str(), 443)) {
    char err[120];
    probe.lastError(err, sizeof(err));
    Serial.printf("3. Secure handshake (443): FAILED -> %s\n", err);
    Serial.printf("   Free memory: %u bytes (needs ~45000)\n", ESP.getFreeHeap());
    return;
  }
  probe.stop();
  Serial.println("3. Secure handshake (443): ok -> the connection works; retrying normally.");
}

void loop() {
  readSerialCommand();

  // WiFi dropped (hotspot turned off, walked away): go dark, reconnect, re-find.
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost.");
    setAll(false);
    shownCount = -1;
    connectWiFi();
    if (!hosted()) findBackend();
  }

  if (backendUrl.length() == 0) {  // search was interrupted by a typed IP; read it
    readSerialCommand();
    if (backendUrl.length() == 0) findBackend();
    return;
  }

  HTTPClient http;
  if (backendUrl.startsWith("https")) {
    http.setTimeout(5000);  // internet + encryption is slower than the local WiFi
    http.setReuse(true);    // keep the secure connection open between polls
    http.begin(secureClient, backendUrl);
  } else {
    http.setTimeout(1000);  // never hang longer than 1 s on a dead laptop
    http.begin(backendUrl);
  }
  int code = http.GET();

  if (code == 200) {
    errorsInARow = 0;
    String body = http.getString();  // e.g. {"count":3,"brightness":0,...,"sos":false,...}

    int at    = body.indexOf("\"count\":");
    int count = at >= 0 ? body.substring(at + 8).toInt() : 0;
    count     = constrain(count, 0, 5);
    bool sos  = body.indexOf("\"sos\":true") >= 0;

    if (sos) {
      bool on = (millis() / 400) % 2 == 0;  // all five flash together
      setAll(on);
      if (on) tone(BUZZER_PIN, 1200, 60);
      if (shownCount != -2) Serial.println("SOS!");
      shownCount = -2;
    } else if (count != shownCount) {
      if (count > shownCount && count > 0) tick();  // tick on the way up
      showFingers(count);
      Serial.printf("fingers = %d\n", count);
      shownCount = count;
    }
  } else {
    // -1 = laptop not found (IP changed / different network / backend stopped)
    // 404 = wrong path (should end in /fingers)
    Serial.printf("backend error %d (%s)\n", code, http.errorToString(code).c_str());
    if (code < 0 && backendUrl.startsWith("https")) {
      secureClient.stop();  // drop the dead connection; the next poll opens a fresh one
      static bool diagnosed = false;
      if (!diagnosed) { diagnosed = true; diagnoseHosted(); }
    }
    if (++errorsInARow >= ERRORS_UNTIL_OFF) {
      setAll(false);  // don't leave stale lights on
      shownCount = -1;
      errorsInARow = 0;
      http.end();
      if (hosted()) {
        Serial.println("Hosted backend not answering (a free server may be waking up, ~1 min).");
        delay(2000);
        return;
      }
      Serial.println("Lost the backend - its IP may have changed. Searching...");
      findBackend();
      return;
    }
  }

  http.end();
  delay(POLL_MS);
}
