/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#pragma once

#include <QMainWindow>
#include <QStackedWidget>

namespace O3DEPilot
{
    class ProjectsScreen;
    class SettingsScreen;

    class MainWindow : public QMainWindow
    {
        Q_OBJECT

    public:
        explicit MainWindow(QWidget* parent = nullptr);
        ~MainWindow() override;

    public slots:
        void ShowProjectsScreen();
        void ShowSettingsScreen();

    private:
        void SetupUI();
        void SetupMenuBar();
        void SetupStatusBar();

        QStackedWidget* m_stackedWidget = nullptr;
        ProjectsScreen* m_projectsScreen = nullptr;
        SettingsScreen* m_settingsScreen = nullptr;
    };

} // namespace O3DEPilot
