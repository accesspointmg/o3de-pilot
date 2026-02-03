/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#pragma once

#include <QString>
#include <QStringList>
#include <QVariant>
#include <functional>
#include <memory>

namespace O3DEPilot
{
    /**
     * PythonBindings provides an interface between the C++ GUI and the Python CLI.
     * It uses the embedded Python interpreter to call o3de_pilot commands.
     */
    class PythonBindings
    {
    public:
        PythonBindings();
        ~PythonBindings();

        bool Initialize();
        void Shutdown();

        // Project operations
        QStringList GetProjects() const;
        bool CreateProject(const QString& name, const QString& path, const QString& templateName);
        bool OpenProject(const QString& path);
        bool BuildProject(const QString& path);

        // Gem operations
        QStringList GetInstalledGems() const;
        QStringList SearchGems(const QString& query) const;
        bool InstallGem(const QString& gemName);
        bool UninstallGem(const QString& gemName);

        // Template operations
        QStringList GetTemplates() const;

        // Engine operations
        QStringList GetRegisteredEngines() const;

        // AI operations
        QString AskAI(const QString& prompt) const;
        bool ConfigureAIProvider(const QString& provider, const QString& apiKey);

        // Registry operations
        QStringList SearchRegistry(const QString& query) const;

        // Async execution with callback
        using ResultCallback = std::function<void(bool success, const QVariant& result)>;
        void ExecuteAsync(const QString& command, const QStringList& args, ResultCallback callback);

    private:
        bool ExecuteCommand(const QString& command, const QStringList& args, QString& output) const;

        class Impl;
        std::unique_ptr<Impl> m_impl;
    };

} // namespace O3DEPilot
