# O3DE Pilot - AI-powered O3DE Project Manager
# SPDX-License-Identifier: Apache-2.0 OR MIT

cmake_minimum_required(VERSION 3.21)

project(O3DEPilot
    VERSION 0.1.0
    DESCRIPTION "AI-powered replacement for O3DE Project Manager"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

# Find Qt6
find_package(Qt6 REQUIRED COMPONENTS
    Core
    Gui
    Widgets
    Network
)

# Find Python for embedded interpreter
find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

# Install Python CLI
install(DIRECTORY src/cli/o3de_pilot
    DESTINATION bin/python
    PATTERN "__pycache__" EXCLUDE
    PATTERN "*.pyc" EXCLUDE
)
