cmake_minimum_required(VERSION 3.4...3.18)

find_package(Python COMPONENTS Interpreter Development)

add_subdirectory(${CMAKE_SOURCE_DIR}/pybind11)

file(GLOB sdk_common
    "${CMAKE_SOURCE_DIR}/../sdk_common/*.h"
    "${CMAKE_SOURCE_DIR}/../sdk_common/*.cpp"
    "${CMAKE_SOURCE_DIR}/../sdk_common/libmodbus/*.h"
    "${CMAKE_SOURCE_DIR}/../sdk_common/libmodbus/*.c"
)

pybind11_add_module(motormaster wrapper.cpp ${sdk_common})

target_compile_definitions(motormaster PRIVATE VERSION_INFO=${SDK_VERSION_INFO})

if(MSVC)
	message("msvc cpp11")
	set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /std:c++latest")
else(MSVC)
	message("gnu cpp11")
	target_compile_features(motormaster PRIVATE cxx_std_17)
endif(MSVC)