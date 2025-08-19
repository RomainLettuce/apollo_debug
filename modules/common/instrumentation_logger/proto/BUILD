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
