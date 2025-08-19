#pragma once

#include <string>
#include <cstdint>
#include <cstdio>  // std::snprintf

// Proto2 schema output from coverage.proto
#include "modules/common/instrumentation_logger/proto/coverage.pb.h"

namespace apollo {
namespace common {

/**
 * @brief Collects per-frame instrumentation data and dumps it as pb.txt.
 *        This singleton is intended for single-threaded (or effectively single-path) use.
 *        No locks/maps are used on the hot path.
 */
class InstrumentationCollector {
public:
  static InstrumentationCollector* Instance();

  // 1) Initialization: set dump directory and ensure it exists.
  void Init(const std::string& dir_name);

  // 2) Frame control: start a new frame with the given index.
  //    Clears the accumulated data for the frame.
  void NewFrame(uint64_t frame_index);

  // 3) Counting APIs (no locks, single-path assumption).
  void FunctionHit(std::string file, std::string func);
  void BranchHit(std::string file, std::string func, std::string branch_id);

  // 4) Dump current frame as "{dir}/{frame_index}.pb.txt".
  bool DumpCurrentFrame();

  // 5) Optional: dump with a custom basename -> "{dir}/{basename}.pb.txt".
  bool DumpToPbTxt(const std::string& basename);

  // 6) Reset the accumulated data for the current frame.
  void Reset();

  // Accessor
  const std::string& dump_dir() const { return dump_dir_; }

private:
  InstrumentationCollector() = default;
  ~InstrumentationCollector() = default;
  InstrumentationCollector(const InstrumentationCollector&) = delete;
  InstrumentationCollector& operator=(const InstrumentationCollector&) = delete;

  // Ensure a FileData exists for the given filename; return a mutable pointer.
  apollo::common::InstrumentationData::FileData*
  EnsureFile(std::string filename);

  // Find counters inside a FileData; return nullptr if not found.
  apollo::common::InstrumentationData::FileData::FunctionData*
  FindFunction(apollo::common::InstrumentationData::FileData* file_msg,
               std::string func_name);

  apollo::common::InstrumentationData::FileData::BranchData*
  FindBranch(apollo::common::InstrumentationData::FileData* file_msg,
             std::string func_name, std::string branch_id);

  // Build "{dir}/{frame_index}.pb.txt".
  std::string MakeFramePath() const;

private:
  std::string dump_dir_;
  uint64_t current_frame_index_ = 0;                 // current frame number
  apollo::common::InstrumentationData data_;         // per-frame accumulation
};

}  // namespace common
}  // namespace apollo

// ---------------------- Convenience Macros ----------------------

#define INSTR_INIT(dir) \
  ::apollo::common::InstrumentationCollector::Instance()->Init((dir))

#define INSTR_NEW_FRAME(idx) \
  ::apollo::common::InstrumentationCollector::Instance()->NewFrame((idx))

#define INSTR_FUNC_HIT() \
  ::apollo::common::InstrumentationCollector::Instance()->FunctionHit(__FILE__, __func__)

#define INSTR_BRANCH_HIT(id) \
  ::apollo::common::InstrumentationCollector::Instance()->BranchHit(__FILE__, __func__, (id))

#define INSTR_BRANCH_HIT_LINE() do { \
  char __instr_br_id[256]; \
  std::snprintf(__instr_br_id, sizeof(__instr_br_id), "%s:%d", __FILE__, __LINE__); \
  ::apollo::common::InstrumentationCollector::Instance()->BranchHit(__FILE__, __func__, __instr_br_id); \
} while (0)

#define INSTR_DUMP_FRAME() \
  ::apollo::common::InstrumentationCollector::Instance()->DumpCurrentFrame()

#define INSTR_DUMP(basename) \
  ::apollo::common::InstrumentationCollector::Instance()->DumpToPbTxt((basename))

#define INSTR_RESET() \
  ::apollo::common::InstrumentationCollector::Instance()->Reset()
