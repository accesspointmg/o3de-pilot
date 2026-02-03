/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#pragma once

#include <QWidget>
#include <QComboBox>
#include <QLineEdit>
#include <QPushButton>

namespace O3DEPilot
{
    class SettingsScreen : public QWidget
    {
        Q_OBJECT

    public:
        explicit SettingsScreen(QWidget* parent = nullptr);
        ~SettingsScreen() override;

    public slots:
        void LoadSettings();
        void SaveSettings();
        void OnAIProviderChanged(int index);

    private:
        void SetupUI();

        // AI Settings
        QComboBox* m_aiProviderCombo = nullptr;
        QLineEdit* m_aiApiKeyEdit = nullptr;
        QLineEdit* m_aiModelEdit = nullptr;
        QLineEdit* m_ollamaUrlEdit = nullptr;

        // Registry Settings
        QLineEdit* m_registryUrlEdit = nullptr;

        QPushButton* m_saveButton = nullptr;
    };

} // namespace O3DEPilot
