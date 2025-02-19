// instrumentation_logger.h
#ifndef INSTRUMENTATION_LOGGER_H
#define INSTRUMENTATION_LOGGER_H

#include <string>
#include <vector>
#include <chrono>
#include <fstream>

namespace apollo {
namespace common {

class InstrumentationLogger {
private:
    static InstrumentationLogger* instance;
    
    struct LogEntry {
        std::string message;
        uint32_t timestamp;
    };
    
    struct CycleData {
        std::vector<LogEntry> entries;
        uint32_t cycleStartTime;
    };
    
    std::vector<CycleData> cycles;
    uint32_t programStartTime;
    std::string fileName;
    
    InstrumentationLogger();
    
    InstrumentationLogger(const InstrumentationLogger&) = delete;
    InstrumentationLogger& operator=(const InstrumentationLogger&) = delete;
    
    uint32_t getCurrentTimestamp();

public:
    static InstrumentationLogger* getInstance();
    
    void log(const std::string& message);
    void newCycle();
    void dumpToFile();
    void setFileName(const std::string& filename);
    
    ~InstrumentationLogger() = default;
};

}
}
#endif // INSTRUMENTATION_LOGGER_H