/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#include "Application.h"
#include "MainWindow.h"
#include "PythonBindings.h"

#include <QMessageBox>
#include <QDir>

namespace O3DEPilot
{
    Application::Application(int& argc, char** argv)
        : QApplication(argc, argv)
    {
    }

    Application::~Application() = default;

    int Application::Run()
    {
        // Initialize Python bindings
        if (!InitializePython())
        {
            QMessageBox::critical(nullptr, "Error", 
                "Failed to initialize Python. Please ensure Python is installed.");
            return 1;
        }

        // Create and show main window
        m_mainWindow = std::make_unique<MainWindow>();
        m_mainWindow->show();

        return exec();
    }

    bool Application::InitializePython()
    {
        m_pythonBindings = std::make_unique<PythonBindings>();
        return m_pythonBindings->Initialize();
    }

} // namespace O3DEPilot
