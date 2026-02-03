/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#include "ProjectsScreen.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QFileDialog>
#include <QMessageBox>

namespace O3DEPilot
{
    ProjectsScreen::ProjectsScreen(QWidget* parent)
        : QWidget(parent)
    {
        SetupUI();
        RefreshProjects();
    }

    ProjectsScreen::~ProjectsScreen() = default;

    void ProjectsScreen::SetupUI()
    {
        QVBoxLayout* mainLayout = new QVBoxLayout(this);

        // Header
        QLabel* titleLabel = new QLabel("Projects", this);
        titleLabel->setStyleSheet("font-size: 24px; font-weight: bold; margin: 10px;");
        mainLayout->addWidget(titleLabel);

        // Button bar
        QHBoxLayout* buttonLayout = new QHBoxLayout();
        
        m_newProjectButton = new QPushButton("New Project", this);
        m_openProjectButton = new QPushButton("Open Project", this);
        m_buildButton = new QPushButton("Build", this);
        m_buildButton->setEnabled(false);

        buttonLayout->addWidget(m_newProjectButton);
        buttonLayout->addWidget(m_openProjectButton);
        buttonLayout->addWidget(m_buildButton);
        buttonLayout->addStretch();

        mainLayout->addLayout(buttonLayout);

        // Project list
        m_projectList = new QListWidget(this);
        m_projectList->setStyleSheet("QListWidget { font-size: 14px; }");
        mainLayout->addWidget(m_projectList);

        // Connections
        connect(m_newProjectButton, &QPushButton::clicked, this, &ProjectsScreen::OnNewProject);
        connect(m_openProjectButton, &QPushButton::clicked, this, &ProjectsScreen::OnOpenProject);
        connect(m_buildButton, &QPushButton::clicked, this, &ProjectsScreen::OnBuildProject);
        connect(m_projectList, &QListWidget::itemClicked, this, &ProjectsScreen::OnProjectSelected);
    }

    void ProjectsScreen::RefreshProjects()
    {
        m_projectList->clear();

        // TODO: Get projects from PythonBindings
        // For now, show placeholder
        m_projectList->addItem("(No projects found - use 'New Project' to create one)");
    }

    void ProjectsScreen::OnNewProject()
    {
        // TODO: Show new project dialog
        QMessageBox::information(this, "New Project", 
            "New Project dialog coming soon!\n\n"
            "This will integrate with the Python CLI to create projects.");
    }

    void ProjectsScreen::OnOpenProject()
    {
        QString dir = QFileDialog::getExistingDirectory(this, "Open Project", 
            QString(), QFileDialog::ShowDirsOnly);
        
        if (!dir.isEmpty())
        {
            // TODO: Open project via PythonBindings
            QMessageBox::information(this, "Open Project", 
                QString("Would open project at: %1").arg(dir));
        }
    }

    void ProjectsScreen::OnBuildProject()
    {
        // TODO: Build selected project
        QMessageBox::information(this, "Build", "Build functionality coming soon!");
    }

    void ProjectsScreen::OnProjectSelected(QListWidgetItem* item)
    {
        m_buildButton->setEnabled(item != nullptr);
    }

} // namespace O3DEPilot
