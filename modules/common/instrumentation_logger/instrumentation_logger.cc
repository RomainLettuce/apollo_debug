#include "modules/common/instrumentation_logger/instrumentation_logger.h"
#include <cstdint>  // for uint32_t
#include <string>
#include <vector>
#include <chrono>
#include <fstream>

namespace apollo {
namespace common {

InstrumentationLogger* InstrumentationLogger::getInstance() {
    if (!instance) {
        instance = new InstrumentationLogger();
    }
    return instance;
}

InstrumentationLogger::InstrumentationLogger() {
    programStartTime = getCurrentTimestamp();
    cycles.push_back(CycleData{});
    cycles.back().cycleStartTime = getCurrentTimestamp();
}

void InstrumentationLogger::log(const std::string& message) {
    uint32_t timestamp = getCurrentTimestamp() - programStartTime;
    cycles.back().entries.push_back({message, timestamp});
}

void InstrumentationLogger::newCycle() {
    cycles.push_back(CycleData{});
    cycles.back().cycleStartTime = getCurrentTimestamp() - programStartTime;
}

void InstrumentationLogger::dumpToFile() {
    if (fileName.empty()) return;

    std::ofstream file(fileName, std::ios::app);
    if (!file.is_open()) return;
    
    for (const auto& cycle : cycles) {
        for (const auto& entry : cycle.entries) {
            file << entry.message << " [+" 
                    << (entry.timestamp - cycle.cycleStartTime) << "ms]\n";
        }
        file << "---------\n";
    }

    cycles.clear();
    cycles.push_back(CycleData{});
    cycles.back().cycleStartTime = getCurrentTimestamp() - programStartTime;
}

void InstrumentationLogger::setFileName(const std::string& filename) {
    fileName = "/apollo/data/instrumentation_log/" + filename;
}
    

uint32_t InstrumentationLogger::getCurrentTimestamp() {
    return static_cast<uint32_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()
        ).count()
    );
}

InstrumentationLogger* InstrumentationLogger::instance = nullptr;

}
}