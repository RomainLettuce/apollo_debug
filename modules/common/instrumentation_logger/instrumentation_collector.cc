#include "instrumentation_collector.h"
#include <string>

#include "cyber/common/file.h"  // EnsureDirectory, GetAbsolutePath, SetProtoToASCIIFile

using apollo::cyber::common::EnsureDirectory;
using apollo::cyber::common::GetAbsolutePath;
using apollo::cyber::common::SetProtoToASCIIFile;

namespace apollo {
namespace common {

InstrumentationCollector* InstrumentationCollector::Instance() {
  static InstrumentationCollector inst;
  return &inst;
}

static inline bool EndsWith(const std::string& s, const std::string& suf) {
  return s.size() >= suf.size() &&
         s.compare(s.size() - suf.size(), suf.size(), suf) == 0;
}

std::string StripTxtSuffix(const std::string& dir_name) {  // 입력은 그대로, 복사본 수정
  std::string name = dir_name;
  const std::string suf = ".txt";
  if (EndsWith(name, suf)) name.erase(name.size() - suf.size());
  return name;
}

void InstrumentationCollector::Init(const std::string& dir_name) {
  // Normalize to absolute path and ensure directory exists.
  dump_dir_ = "/apollo/data/coverage/" + StripTxtSuffix(dir_name);
  EnsureDirectory(dump_dir_);
}

void InstrumentationCollector::NewFrame(uint64_t frame_index) {
  // Start a new frame: set index and clear previous data.
  current_frame_index_ = frame_index;
  data_.clear_files();
}

apollo::common::InstrumentationData::FileData*
InstrumentationCollector::EnsureFile(std::string filename) {
  // Linear search: reuse if filename match; otherwise append a new entry.
  for (int i = 0; i < data_.files_size(); ++i) {
    auto* f = data_.mutable_files(i);
    if (f->has_filename() && f->filename() == filename) {
      return f;
    }
  }
  auto* f = data_.add_files();
  f->set_filename(filename);
  return f;
}

apollo::common::InstrumentationData::FileData::FunctionData*
InstrumentationCollector::FindFunction(apollo::common::InstrumentationData::FileData* file_msg,
                                       std::string func_name) {
  const int n = file_msg->function_calls_size();
  for (int i = 0; i < n; ++i) {
    auto* fn = file_msg->mutable_function_calls(i);
    if (fn->has_function_name() && fn->function_name() == func_name) {
      return fn;
    }
  }
  return nullptr;
}

apollo::common::InstrumentationData::FileData::BranchData*
InstrumentationCollector::FindBranch(apollo::common::InstrumentationData::FileData* file_msg,
                                     std::string func_name, std::string branch_id) {
  const int n = file_msg->branch_coverage_size();
  for (int i = 0; i < n; ++i) {
    auto* br = file_msg->mutable_branch_coverage(i);
    if (br->has_function_name() && br->has_branch_id() &&
        br->function_name() == func_name && br->branch_id() == branch_id) {
      return br;
    }
  }
  return nullptr;
}

void InstrumentationCollector::FunctionHit(std::string file, std::string func) {
  // Increment total_calls for (file, func); create on first use.
  auto* fmsg = EnsureFile(file);
  auto* fn = FindFunction(fmsg, func);
  if (fn) {
    fn->set_total_calls(fn->total_calls() + 1);
  } else {
    auto* add = fmsg->add_function_calls();
    add->set_function_name(func);
    add->set_total_calls(1);
  }
}

void InstrumentationCollector::BranchHit(std::string file,
                                         std::string func,
                                         std::string branch_id) {
  // Increment total_hits for (file, func, branch_id); create on first use.
  auto* fmsg = EnsureFile(file);
  auto* br = FindBranch(fmsg, func, branch_id);
  if (br) {
    br->set_total_hits(br->total_hits() + 1);
  } else {
    auto* add = fmsg->add_branch_coverage();
    add->set_function_name(func);
    add->set_branch_id(branch_id);
    add->set_total_hits(1);
  }
}

std::string InstrumentationCollector::MakeFramePath() const {
  // "{dir}/{frame_index}.pb.txt"
  return GetAbsolutePath(dump_dir_, std::to_string(current_frame_index_) + ".pb.txt");
}

bool InstrumentationCollector::DumpCurrentFrame() {
  if (dump_dir_.empty()) return false;
  return SetProtoToASCIIFile(data_, MakeFramePath());
}

bool InstrumentationCollector::DumpToPbTxt(const std::string& basename) {
  if (dump_dir_.empty() || basename.empty()) return false;
  const std::string out_path = GetAbsolutePath(dump_dir_, basename + ".pb.txt");
  return SetProtoToASCIIFile(data_, out_path);
}

void InstrumentationCollector::Reset() {
  // Clear current frame’s accumulated data.
  data_.clear_files();
}

}  // namespace common
}  // namespace apollo
