load("@rules_proto//proto:defs.bzl", "proto_library")
load("@rules_cc//cc:defs.bzl", "cc_proto_library")
load("//tools:python_rules.bzl", "py_proto_library")

package(default_visibility = ["//visibility:public"])

cc_proto_library(
    name = "coverage_cc_proto",
    deps = [
        ":coverage_proto",
    ],
)

proto_library(
    name = "coverage_proto",
    srcs = ["coverage.proto"],
    deps = [],
)

py_proto_library(
    name = "coverage_py_pb2",
    deps = [
        ":coverage_proto",],
)

cc_proto_library(
    name = "replay_debug_cc_proto",
    deps = [
        ":replay_debug_proto",
    ],
)

proto_library(
    name = "replay_debug_proto",
    srcs = ["replay_debug.proto"],
    deps = [
        "//modules/routing/proto:routing_proto",
        "//modules/planning/proto:planning_proto",
        "//modules/planning/proto:planning_status_proto",
    ],
)

py_proto_library(
    name = "replay_debug_py_pb2",
    deps = [
        ":replay_debug_proto",
        "//modules/routing/proto:routing_py_pb2",
        "//modules/planning/proto:planning_py_pb2",
        "//modules/planning/proto:planning_status_py_pb2",
    ],
)