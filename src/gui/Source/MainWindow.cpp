/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#include "MainWindow.h"
#include "ProjectsScreen.h"
#include "SettingsScreen.h"

#include <QMenuBar>
#include <QStatusBar>
#include <QVBoxLayout>

namespace O3DEPilot
{
    MainWindow::MainWindow(QWidget* parent)
        : QMainWindow(parent)
    {
        SetupUI();
        SetupMenuBar();
        SetupStatusBar();

        setWindowTitle("O3DE Pilot");
        resize(1200, 800);
    }

    MainWindow::~MainWindow() = default;

    void MainWindow::SetupUI()
    {
        m_stackedWidget = new QStackedWidget(this);
        setCentralWidget(m_stackedWidget);

        // Create screens
        m_projectsScreen = new ProjectsScreen(this);
        m_settingsScreen = new SettingsScreen(this);

        m_stackedWidget->addWidget(m_projectsScreen);
        m_stackedWidget->addWidget(m_settingsScreen);

        // Start with projects screen
        ShowProjectsScreen();
    }

    void MainWindow::SetupMenuBar()
    {
        QMenuBar* menuBar = this->menuBar();

        // File menu
        QMenu* fileMenu = menuBar->addMenu("&File");
        fileMenu->addAction("&New Project...", this, []() {
            // TODO: Implement new project dialog
        });
        fileMenu->addAction("&Open Project...", this, []() {
            // TODO: Implement open project dialog
        });
        fileMenu->addSeparator();
        fileMenu->addAction("E&xit", this, &QMainWindow::close);

        // View menu
        QMenu* viewMenu = menuBar->addMenu("&View");
        viewMenu->addAction("&Projects", this, &MainWindow::ShowProjectsScreen);
        viewMenu->addAction("&Settings", this, &MainWindow::ShowSettingsScreen);

        // AI menu
        QMenu* aiMenu = menuBar->addMenu("&AI");
        aiMenu->addAction("&Ask AI...", this, []() {
            // TODO: Implement AI chat dialog
        });
        aiMenu->addAction("&Configure AI Provider...", this, []() {
            // TODO: Implement AI settings
        });

        // Help menu
        QMenu* helpMenu = menuBar->addMenu("&Help");
        helpMenu->addAction("&Documentation", this, []() {
            // TODO: Open docs
        });
        helpMenu->addAction("&About O3DE Pilot", this, []() {
            // TODO: Show about dialog
        });
    }

    void MainWindow::SetupStatusBar()
    {
        statusBar()->showMessage("Ready");
    }

    void MainWindow::ShowProjectsScreen()
    {
        m_stackedWidget->setCurrentWidget(m_projectsScreen);
    }

    void MainWindow::ShowSettingsScreen()
    {
        m_stackedWidget->setCurrentWidget(m_settingsScreen);
    }

} // namespace O3DEPilot
