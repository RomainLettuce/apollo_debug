load("@rules_cc//cc:defs.bzl", "cc_library")
load("//tools:cpplint.bzl", "cpplint")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "instrumentation_collector",
    srcs = ["instrumentation_collector.cc"],
    hdrs = ["instrumentation_collector.h"],
    deps = ["//cyber/common:file",
            "//modules/common/instrumentation_logger/proto:coverage_cc_proto",
    ],
)

cc_library(
    name = "dumper",
    srcs = ["dumper.cc"],
    hdrs = ["dumper.h"],
    deps = ["//cyber/common:file",
            "//modules/routing/proto:routing_cc_proto",
            "//modules/planning/proto:planning_cc_proto",
            "//modules/planning/proto:planning_status_cc_proto",
            "//modules/common/instrumentation_logger/proto:replay_debug_cc_proto",
    ],
)


cpplint()
