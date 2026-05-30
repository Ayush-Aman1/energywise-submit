cmake_minimum_required(VERSION 3.13.4)
project(EnergyWise LANGUAGES CXX)

# -----------------------------------------------------------------------------
# Build as an LLVM out-of-tree plugin (new pass manager).
# Usage:
#   mkdir build && cd build
#   cmake -DLT_LLVM_INSTALL_DIR=$(llvm-config --prefix) ..
#   make
# Then:
#   opt -load-pass-plugin ./libEnergyWise.so -passes=energywise \
#       -energy-model=../../models/rv32imc_energy.yaml \
#       -energy-report=../../reports/report.json bench.ll
# -----------------------------------------------------------------------------

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Allow user to pass -DLT_LLVM_INSTALL_DIR=... if not using system llvm-config.
if(DEFINED LT_LLVM_INSTALL_DIR)
  list(APPEND CMAKE_PREFIX_PATH "${LT_LLVM_INSTALL_DIR}/lib/cmake/llvm/")
endif()

find_package(LLVM 15 CONFIG)
if(NOT LLVM_FOUND)
  find_package(LLVM 16 CONFIG)
endif()
if(NOT LLVM_FOUND)
  find_package(LLVM 17 CONFIG REQUIRED)
endif()

message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")

include_directories(SYSTEM ${LLVM_INCLUDE_DIRS})
separate_arguments(LLVM_DEFINITIONS_LIST NATIVE_COMMAND ${LLVM_DEFINITIONS})
add_definitions(${LLVM_DEFINITIONS_LIST})

# Match LLVM build flags (RTTI/exceptions). LLVM is typically built -fno-rtti.
if(NOT LLVM_ENABLE_RTTI)
  set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fno-rtti")
endif()
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fvisibility-inlines-hidden")

add_library(EnergyWise SHARED EnergyEstimationPass.cpp)
target_link_libraries(EnergyWise PRIVATE LLVMCore LLVMSupport LLVMAnalysis LLVMPasses)

# Don't prefix "lib" on macOS/Linux to match LLVM convention for plugins.
set_target_properties(EnergyWise PROPERTIES PREFIX "lib")
