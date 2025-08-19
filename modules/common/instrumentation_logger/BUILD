load("@rules_cc//cc:defs.bzl", "cc_library")
load("//tools:cpplint.bzl", "cpplint")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "instrumentation_logger",
    srcs = ["instrumentation_logger.cc"],
    hdrs = ["instrumentation_logger.h"],
    deps = [],
)

cc_library(
    name = "instrumentation_collector",
    srcs = ["instrumentation_collector.cc"],
    hdrs = ["instrumentation_collector.h"],
    deps = ["//cyber/common:file",
            "//modules/common/instrumentation_logger/proto:coverage_cc_proto",
    ],
)

cpplint()
