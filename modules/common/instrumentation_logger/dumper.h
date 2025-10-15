#pragma once
#include <cstdint>
#include <string>
#include <utility>

#include "modules/common/instrumentation_logger/proto/replay_debug.pb.h"
#include "modules/routing/proto/routing.pb.h"
#include "modules/planning/proto/planning_status.pb.h"
#include "modules/planning/proto/planning.pb.h"

namespace apollo {
namespace common {

class Dumper {
 public:
  static Dumper* Instance();

  void Init(const std::string& dir_name);
  void NewFrame(uint64_t frame_index);

  void SetCore(const apollo::routing::RoutingResponse& last_routing,
               const apollo::planning::PlanningStatus& planning_status,
               const apollo::planning::ADCTrajectory& traj);

  void SetPathOptFailure(bool v);
  void SetSpeedOptFailure(bool v);

  bool DumpCurrentFrame();
  bool DumpToPbTxt(const std::string& basename);
  void Reset();

 private:
  Dumper() = default;
  ~Dumper() = default;
  Dumper(const Dumper&) = delete;
  Dumper& operator=(const Dumper&) = delete;

  std::string MakeFramePath() const;

 private:
  std::string dump_dir_;
  uint64_t current_frame_index_ = 0;
  apollo::common::ReplayInfo info_;
};

}  // namespace common
}  // namespace apollo

#ifndef DUMP_ENABLE
#define DUMP_ENABLE 1
#endif

#if DUMP_ENABLE == 1

  #define DUMP_INIT(dir) \
    ::apollo::common::Dumper::Instance()->Init((dir))
  #define DUMP_NEW_FRAME(idx) \
    ::apollo::common::Dumper::Instance()->NewFrame((idx))
  #define DUMP_SET_CORE(last_routing, planning_status, traj) \
    ::apollo::common::Dumper::Instance()->SetCore((last_routing),(planning_status),(traj))
  #define DUMP_SET_PATH_OPT_FAILURE(v) \
    ::apollo::common::Dumper::Instance()->SetPathOptFailure((v))
  #define DUMP_SET_SPEED_OPT_FAILURE(v) \
    ::apollo::common::Dumper::Instance()->SetSpeedOptFailure((v))
  #define DUMP_DUMP_FRAME() \
    ::apollo::common::Dumper::Instance()->DumpCurrentFrame()
  #define DUMP_DUMP(basename) \
    ::apollo::common::Dumper::Instance()->DumpToPbTxt((basename))
  #define DUMP_RESET() \
    ::apollo::common::Dumper::Instance()->Reset()

#else  // DUMP_ENABLE != 1

  #define DUMP_INIT(dir)                        do { (void)sizeof(dir); } while (0)
  #define DUMP_NEW_FRAME(idx)                   do { (void)sizeof(idx); } while (0)
  #define DUMP_SET_CORE(a,b,c)                  do { (void)sizeof(a); (void)sizeof(b); (void)sizeof(c); } while (0)
  #define DUMP_SET_PATH_OPT_FAILURE(v)          do { (void)sizeof(v); } while (0)
  #define DUMP_SET_SPEED_OPT_FAILURE(v)         do { (void)sizeof(v); } while (0)
  #define DUMP_DUMP_FRAME()                     do { } while (0)
  #define DUMP_DUMP(basename)                   do { (void)sizeof(basename); } while (0)
  #define DUMP_RESET()                          do { } while (0)

#endif
