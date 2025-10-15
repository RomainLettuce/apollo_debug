#include "dumper.h"

#include "cyber/common/file.h"

using apollo::cyber::common::EnsureDirectory;
using apollo::cyber::common::GetAbsolutePath;
using apollo::cyber::common::SetProtoToASCIIFile;

namespace apollo {
namespace common {

Dumper* Dumper::Instance() {
  static Dumper inst;
  return &inst;
}

static inline bool EndsWith(const std::string& s, const std::string& suf) {
  return s.size() >= suf.size() &&
         s.compare(s.size() - suf.size(), suf.size(), suf) == 0;
}

static std::string StripTxtSuffix(const std::string& dir_name) {
  std::string name = dir_name;
  const std::string suf = ".txt";
  if (EndsWith(name, suf)) name.erase(name.size() - suf.size());
  return name;
}

void Dumper::Init(const std::string& dir_name) {
  dump_dir_ = "/apollo/data/replay/" + StripTxtSuffix(dir_name);
  EnsureDirectory(dump_dir_);
}

void Dumper::NewFrame(uint64_t frame_index) {
  current_frame_index_ = frame_index;
  info_.Clear();
}

void Dumper::SetCore(const apollo::routing::RoutingResponse& last_routing,
                                   const apollo::planning::PlanningStatus& planning_status,
                                   const apollo::planning::ADCTrajectory& traj) {
  *info_.mutable_last_routing() = last_routing;
  *info_.mutable_planning_status() = planning_status;
  *info_.mutable_traj() = traj;
}

void Dumper::SetPathOptFailure(bool v)  { info_.set_path_opt_failure(v); }
void Dumper::SetSpeedOptFailure(bool v) { info_.set_speed_opt_failure(v); }

std::string Dumper::MakeFramePath() const {
  return GetAbsolutePath(dump_dir_, std::to_string(current_frame_index_) + ".pb.txt");
}

bool Dumper::DumpCurrentFrame() {
  if (dump_dir_.empty()) return false;
  return SetProtoToASCIIFile(info_, MakeFramePath());
}

bool Dumper::DumpToPbTxt(const std::string& basename) {
  if (dump_dir_.empty() || basename.empty()) return false;
  const std::string out = GetAbsolutePath(dump_dir_, basename + ".pb.txt");
  return SetProtoToASCIIFile(info_, out);
}

void Dumper::Reset() { info_.Clear(); }

}  // namespace common
}  // namespace apollo
