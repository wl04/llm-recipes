#include <hip/hip_runtime.h>
#include <cstdio>
#include <cstring>
#include <stdexcept>

static void check(hipError_t result) {
    if (result != hipSuccess) throw std::runtime_error(hipGetErrorString(result));
}
__global__ void increment(int* value) { *value += 1; }
int main() {
    try {
        int count = 0, selected = -1;
        check(hipGetDeviceCount(&count));
        hipDeviceProp_t properties{};
        for (int i = 0; i < count; ++i) {
            check(hipGetDeviceProperties(&properties, i));
            if (std::strncmp(properties.gcnArchName, "gfx1201", 7) == 0) {
                if (selected >= 0) throw std::runtime_error("Multiple gfx1201 GPUs: set HIP_VISIBLE_DEVICES");
                selected = i;
            }
        }
        if (selected < 0) throw std::runtime_error("No gfx1201 GPU detected");
        check(hipSetDevice(selected));
        check(hipGetDeviceProperties(&properties, selected));
        int* device = nullptr;
        check(hipMalloc(&device, sizeof(int)));
        check(hipMemset(device, 0, sizeof(int)));
        hipLaunchKernelGGL(increment, dim3(1), dim3(1), 0, 0, device);
        check(hipGetLastError());
        check(hipDeviceSynchronize());
        int value = 0;
        check(hipMemcpy(&value, device, sizeof(int), hipMemcpyDeviceToHost));
        check(hipFree(device));
        if (value != 1) throw std::runtime_error("HIP kernel returned the wrong result");
        std::printf("{\"device\":%d,\"architecture\":\"gfx1201\",\"vram_bytes\":%zu,\"kernel\":\"PASS\"}\n",
                    selected, properties.totalGlobalMem);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "HIP check failed: %s\n", error.what());
        return 1;
    }
}
