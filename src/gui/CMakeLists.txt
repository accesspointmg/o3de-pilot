# O3DE Pilot GUI
# SPDX-License-Identifier: Apache-2.0 OR MIT

set(TARGET_NAME O3DEPilot)

set(SOURCES
    Source/main.cpp
    Source/Application.cpp
    Source/Application.h
    Source/MainWindow.cpp
    Source/MainWindow.h
    Source/PythonBindings.cpp
    Source/PythonBindings.h
    Source/ProjectsScreen.cpp
    Source/ProjectsScreen.h
    Source/SettingsScreen.cpp
    Source/SettingsScreen.h
)

set(RESOURCES
    Resources/resources.qrc
)

add_executable(${TARGET_NAME}
    ${SOURCES}
    ${RESOURCES}
)

target_include_directories(${TARGET_NAME} PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/Source
    ${Python3_INCLUDE_DIRS}
)

target_link_libraries(${TARGET_NAME} PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    Qt6::Network
    ${Python3_LIBRARIES}
)

# Platform-specific settings
if(WIN32)
    set_target_properties(${TARGET_NAME} PROPERTIES
        WIN32_EXECUTABLE TRUE
    )
endif()

if(APPLE)
    set_target_properties(${TARGET_NAME} PROPERTIES
        MACOSX_BUNDLE TRUE
        MACOSX_BUNDLE_INFO_PLIST ${CMAKE_CURRENT_SOURCE_DIR}/Platform/Mac/Info.plist.in
    )
endif()

# Install
install(TARGETS ${TARGET_NAME}
    RUNTIME DESTINATION bin
    BUNDLE DESTINATION bin
)
