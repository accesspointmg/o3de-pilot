/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#pragma once

#include <QWidget>
#include <QListWidget>
#include <QPushButton>

namespace O3DEPilot
{
    class ProjectsScreen : public QWidget
    {
        Q_OBJECT

    public:
        explicit ProjectsScreen(QWidget* parent = nullptr);
        ~ProjectsScreen() override;

    public slots:
        void RefreshProjects();
        void OnNewProject();
        void OnOpenProject();
        void OnBuildProject();
        void OnProjectSelected(QListWidgetItem* item);

    private:
        void SetupUI();

        QListWidget* m_projectList = nullptr;
        QPushButton* m_newProjectButton = nullptr;
        QPushButton* m_openProjectButton = nullptr;
        QPushButton* m_buildButton = nullptr;
    };

} // namespace O3DEPilot
