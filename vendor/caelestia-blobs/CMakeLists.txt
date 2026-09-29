cmake_minimum_required(VERSION 3.25)
project(OmarchySetupCaelestiaBlobs LANGUAGES CXX)

find_package(Qt6 6.9 REQUIRED COMPONENTS Core Gui Qml Quick ShaderTools)

qt_standard_project_setup(REQUIRES 6.9)
set(QT_QML_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/qml")

add_subdirectory(Blobs)
