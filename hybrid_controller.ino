// ESP32 hybrid wind+solar controller skeleton (TFLite Micro). NOT TESTED ON HARDWARE.
// Models were trained on SIMULATED data: recalibrate/retrain with real logs before controlling a real battery.
// Library: "TensorFlowLite_ESP32" (Arduino Library Manager) or esp-tflite-micro.
#include <TensorFlowLite_ESP32.h>
#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "models.h"
#include "norms.h"
#include <math.h>

constexpr int ARENA = 20 * 1024;
static uint8_t arena_f[ARENA], arena_x[ARENA], arena_d[ARENA];
tflite::AllOpsResolver resolver;
tflite::MicroInterpreter *itF, *itX, *itD;

static tflite::MicroInterpreter* make(const unsigned char* m, uint8_t* a) {
  const tflite::Model* model = tflite::GetModel(m);
  auto* it = new tflite::MicroInterpreter(model, resolver, a, ARENA);
  it->AllocateTensors();
  return it;
}
float clearSky(float h) { return (h > 6 && h < 18) ? 1000.0f * powf(fmaxf(0, sinf(M_PI * (h - 6) / 12)), 1.2f) : 0; }
// wind expected power (W) from the project's table (sheet 3/7), x boost efficiency 0.9
float windExpected(float ws) {
  static const float V[] = {1.9,2.32,2.5,2.64,2.92,2.96,3.28,3.33,3.6,3.75,3.92,4.17,4.24,4.56,4.58,4.88,5.0,5.2,5.42,5.83,6.5,7.5};
  static const float P[] = {0,2.49,3.23,3.95,5.46,5.79,8.06,8.55,10.93,12.38,14.31,17.29,18.23,22.70,23.09,27.99,30.16,33.93,38.37,47.92,60,60};
  const int n = 22; if (ws <= V[0]) return 0; if (ws >= V[n-1]) return P[n-1] * 0.9f;
  for (int i = 1; i < n; i++) if (ws <= V[i]) return (P[i-1] + (P[i]-P[i-1]) * (ws - V[i-1]) / (V[i]-V[i-1])) * 0.9f;
  return 0;
}
// int8 helper
static void runInt8(tflite::MicroInterpreter* it, const float* x, int n, const float* mu, const float* sd, float* out, int nout) {
  TfLiteTensor* in = it->input(0); float s = in->params.scale; int z = in->params.zero_point;
  for (int i = 0; i < n; i++) { int q = lroundf(((x[i]-mu[i])/sd[i]) / s + z); in->data.int8[i] = (int8_t)constrain(q, -128, 127); }
  it->Invoke();
  TfLiteTensor* o = it->output(0);
  for (int i = 0; i < nout; i++) out[i] = (o->data.int8[i] - o->params.zero_point) * o->params.scale;
}
// next-hour generation forecast (W). g=irradiance, ws=wind, hour=local hour; gen[0..6]= last 7 samples of PV+wind power (10-min steps, newest last)
float forecastHour(const float gen[7], float g, float ws, float hour) {
  float c0 = clearSky(hour), c1 = clearSky(hour + 1), k = constrain(g / (c0 + 10), 0, 1.5f), m6 = 0;
  for (int i = 1; i < 7; i++) m6 += gen[i]; m6 /= 6;
  float x[13] = {gen[6], gen[5], gen[3], gen[0], m6, k, c0, c1, ws, powf(fminf(ws, 8), 3) / 100.0f,
                 constrain(0.4674f * k * c1, 0, 700), sinf(2*M_PI*hour/24), cosf(2*M_PI*hour/24)};
  float y; runInt8(itF, x, 13, FC_MU, FC_SD, &y, 1); return fmaxf(0, y * 100.0f);
}
// fault class: 0 normal,1 PV loss,2 wind stall,3 vbat sensor stuck,4 battery overheat. Inputs = averages/std over the last hour (6 samples)
int faultClass(float g, float pv, float ws, float wp, float dT, float stdV, float meanAbsI, float stdI) {
  float rpv = g > 200 ? constrain(pv / (0.4674f * g + 1e-6f), 0, 1.5f) : 1.0f;
  float rw  = ws > 3.5f ? constrain(wp / (windExpected(ws) + 1e-6f), 0, 2.0f) : 1.0f;
  float x[7] = {rpv, rw, dT, stdV, meanAbsI, stdI, (stdV < 0.01f && stdI > 0.2f) ? 1.0f : 0.0f}, p[5];
  runInt8(itX, x, 7, FA_MU, FA_SD, p, 5); int b = 0; for (int i = 1; i < 5; i++) if (p[i] > p[b]) b = i; return b;
}
// dispatch action: 0 serve critical+non-critical, 1 + deferrable load, 2 critical only (float32 model)
int dispatchAction(float soc, float hour, float critW, float noncW, float genW, float gen1hW, float flexWh, float ws) {
  float s[10] = {soc, sinf(2*M_PI*hour/24), cosf(2*M_PI*hour/24), critW/200, noncW/300, genW/700, gen1hW/700, clearSky(hour+1)/1000, flexWh/500, ws/12};
  for (int i = 0; i < 10; i++) itD->input(0)->data.f[i] = s[i];
  itD->Invoke(); int b = 0; for (int i = 1; i < 3; i++) if (itD->output(0)->data.f[i] > itD->output(0)->data.f[b]) b = i; return b;
}
void setup() {
  Serial.begin(115200);
  itF = make(forecast_model, arena_f); itX = make(fault_model, arena_x); itD = make(dqn_model, arena_d);
  // TODO: read your real sensors (INA226/ACS712 for V/I, DS18B20 for temperature, anemometer, pyranometer or reference cell)
  // and map the action to relays/MOSFETs. ALWAYS keep a hardware BMS/fuse and a hard-coded safety layer outside the AI.
}
void loop() {
  // demo with fixed numbers (replace with real sensor reads every 10 minutes)
  float gen[7] = {300,310,320,330,340,350,360};
  Serial.printf("forecast=%.0fW fault=%d action=%d\n", forecastHour(gen, 700, 3.5f, 11.0f),
                faultClass(800, 370, 4.5f, 19, 1, 0.05f, 5, 1), dispatchAction(0.35f, 19, 80, 120, 40, 60, 500, 3));
  delay(600000);
}
