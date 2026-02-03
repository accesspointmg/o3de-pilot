/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#pragma once

#include <QApplication>
#include <memory>

namespace O3DEPilot
{
    class MainWindow;
    class PythonBindings;

    class Application : public QApplication
    {
        Q_OBJECT

    public:
        Application(int& argc, char** argv);
        ~Application() override;

        int Run();

        PythonBindings* GetPythonBindings() const { return m_pythonBindings.get(); }

    private:
        bool InitializePython();

        std::unique_ptr<MainWindow> m_mainWindow;
        std::unique_ptr<PythonBindings> m_pythonBindings;
    };

} // namespace O3DEPilot
