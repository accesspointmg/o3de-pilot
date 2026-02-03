/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#include "SettingsScreen.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFormLayout>
#include <QGroupBox>
#include <QLabel>
#include <QMessageBox>

namespace O3DEPilot
{
    SettingsScreen::SettingsScreen(QWidget* parent)
        : QWidget(parent)
    {
        SetupUI();
        LoadSettings();
    }

    SettingsScreen::~SettingsScreen() = default;

    void SettingsScreen::SetupUI()
    {
        QVBoxLayout* mainLayout = new QVBoxLayout(this);

        // Header
        QLabel* titleLabel = new QLabel("Settings", this);
        titleLabel->setStyleSheet("font-size: 24px; font-weight: bold; margin: 10px;");
        mainLayout->addWidget(titleLabel);

        // AI Settings Group
        QGroupBox* aiGroup = new QGroupBox("AI Configuration", this);
        QFormLayout* aiLayout = new QFormLayout(aiGroup);

        m_aiProviderCombo = new QComboBox(this);
        m_aiProviderCombo->addItems({"Claude (Anthropic)", "OpenAI", "Ollama (Local)", "None"});
        aiLayout->addRow("AI Provider:", m_aiProviderCombo);

        m_aiApiKeyEdit = new QLineEdit(this);
        m_aiApiKeyEdit->setEchoMode(QLineEdit::Password);
        m_aiApiKeyEdit->setPlaceholderText("Enter API key...");
        aiLayout->addRow("API Key:", m_aiApiKeyEdit);

        m_aiModelEdit = new QLineEdit(this);
        m_aiModelEdit->setPlaceholderText("e.g., claude-3-opus, gpt-4, llama3");
        aiLayout->addRow("Model:", m_aiModelEdit);

        m_ollamaUrlEdit = new QLineEdit(this);
        m_ollamaUrlEdit->setPlaceholderText("http://localhost:11434");
        m_ollamaUrlEdit->setEnabled(false);
        aiLayout->addRow("Ollama URL:", m_ollamaUrlEdit);

        mainLayout->addWidget(aiGroup);

        // Registry Settings Group
        QGroupBox* registryGroup = new QGroupBox("Registry Configuration", this);
        QFormLayout* registryLayout = new QFormLayout(registryGroup);

        m_registryUrlEdit = new QLineEdit(this);
        m_registryUrlEdit->setPlaceholderText("https://canonical.o3de.org");
        registryLayout->addRow("Registry URL:", m_registryUrlEdit);

        mainLayout->addWidget(registryGroup);

        // Save button
        QHBoxLayout* buttonLayout = new QHBoxLayout();
        m_saveButton = new QPushButton("Save Settings", this);
        buttonLayout->addStretch();
        buttonLayout->addWidget(m_saveButton);
        mainLayout->addLayout(buttonLayout);

        mainLayout->addStretch();

        // Connections
        connect(m_aiProviderCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                this, &SettingsScreen::OnAIProviderChanged);
        connect(m_saveButton, &QPushButton::clicked, this, &SettingsScreen::SaveSettings);
    }

    void SettingsScreen::LoadSettings()
    {
        // TODO: Load from PythonBindings / config file
        m_aiProviderCombo->setCurrentIndex(0);
        m_registryUrlEdit->setText("https://canonical.o3de.org");
    }

    void SettingsScreen::SaveSettings()
    {
        // TODO: Save via PythonBindings
        QMessageBox::information(this, "Settings", "Settings saved successfully!");
    }

    void SettingsScreen::OnAIProviderChanged(int index)
    {
        // Show/hide fields based on provider
        bool needsApiKey = (index == 0 || index == 1); // Claude or OpenAI
        bool isOllama = (index == 2);

        m_aiApiKeyEdit->setEnabled(needsApiKey);
        m_ollamaUrlEdit->setEnabled(isOllama);
    }

} // namespace O3DEPilot
