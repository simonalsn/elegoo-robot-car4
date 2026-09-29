// Local ELEGOO bring-up extension. JPEG datagrams, protocol documented in docs/udp-video.md.
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include "esp_camera.h"

static void put32(uint8_t *p, uint32_t n) {
  p[0] = n >> 24; p[1] = n >> 16; p[2] = n >> 8; p[3] = n;
}
static void put16(uint8_t *p, uint16_t n) { p[0] = n >> 8; p[1] = n; }
static void videoTask(void *) {
  WiFiUDP udp;
  while (!udp.begin(5000)) vTaskDelay(pdMS_TO_TICKS(1000));
  IPAddress peer;
  uint16_t port = 0;
  uint8_t token[4] = {};
  uint32_t renewed = 0, frame = 0;
  uint8_t packet[1220];
  for (;;) {
    bool active = port && uint32_t(millis() - renewed) < 3000;
    // Bound subscription processing so stray traffic cannot starve capture.
    for (int n = 0; n < 8 && udp.parsePacket(); ++n) {
      uint8_t request[9];
      int len = udp.read(request, sizeof(request));
      bool owner = len == 8 && active && udp.remoteIP() == peer && udp.remotePort() == port
                   && !memcmp(request + 4, token, 4);
      if (len == 8 && !memcmp(request, "EVS1", 4) && (!active || owner)) {
        peer = udp.remoteIP(); port = udp.remotePort();
        memcpy(token, request + 4, 4); renewed = millis(); active = true;
      } else if (len == 8 && owner && !memcmp(request, "EVX1", 4)) {
        port = 0; active = false;
      }
      udp.flush();
    }
    if (!active || WiFi.status() != WL_CONNECTED) {
      vTaskDelay(pdMS_TO_TICKS(20)); continue;
    }
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) { vTaskDelay(pdMS_TO_TICKS(20)); continue; }
    ++frame;
    // Bound frame size and skip malformed JPEGs rather than displaying corruption.
    if (fb->format == PIXFORMAT_JPEG && fb->len >= 4 && fb->len <= 262144
        && fb->buf[0] == 0xff && fb->buf[1] == 0xd8
        && fb->buf[fb->len-2] == 0xff && fb->buf[fb->len-1] == 0xd9) {
      uint16_t count = (fb->len + 1199) / 1200;
      memcpy(packet, "EVF1", 4); memcpy(packet + 4, token, 4);
      put32(packet + 8, frame); put32(packet + 12, fb->len);
      put16(packet + 18, count);
      for (uint16_t i = 0; i < count; ++i) {
        size_t offset = size_t(i) * 1200;
        size_t size = min(size_t(1200), fb->len - offset);
        put16(packet + 16, i); memcpy(packet + 20, fb->buf + offset, size);
        if (!udp.beginPacket(peer, port)) break;
        if (udp.write(packet, size + 20) != size + 20 || !udp.endPacket()) break;
        // Yield between bursts to avoid filling Wi-Fi transmit buffers.
        if ((i & 7) == 7) vTaskDelay(1);
      }
    }
    esp_camera_fb_return(fb);
    vTaskDelay(1);
  }
}
void startUdpVideo() {
  // Same WROVER camera mapping and JPEG configuration; independent of control TCP.
  WiFi.setSleep(false);
  if (xTaskCreate(videoTask, "udp-video", 4096, nullptr, 1, nullptr) != pdPASS)
    Serial.println("UDP video task creation failed");
}
