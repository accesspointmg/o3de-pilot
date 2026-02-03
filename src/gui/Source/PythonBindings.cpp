/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#include "PythonBindings.h"

#include <QProcess>
#include <QCoreApplication>
#include <QDir>
#include <QThread>
#include <QDebug>

namespace O3DEPilot
{
    class PythonBindings::Impl
    {
    public:
        QString pythonPath;
        QString cliModulePath;
        bool initialized = false;
    };

    PythonBindings::PythonBindings()
        : m_impl(std::make_unique<Impl>())
    {
    }

    PythonBindings::~PythonBindings()
    {
        Shutdown();
    }

    bool PythonBindings::Initialize()
    {
        // Find Python executable
        #ifdef Q_OS_WIN
        m_impl->pythonPath = "python";
        #else
        m_impl->pythonPath = "python3";
        #endif

        // Find CLI module path (relative to executable)
        QString appDir = QCoreApplication::applicationDirPath();
        m_impl->cliModulePath = QDir(appDir).filePath("python/o3de_pilot");

        // Verify Python is available
        QProcess process;
        process.start(m_impl->pythonPath, {"--version"});
        process.waitForFinished();
        
        if (process.exitCode() != 0)
        {
            qWarning() << "Python not found";
            return false;
        }

        m_impl->initialized = true;
        qDebug() << "Python bindings initialized";
        return true;
    }

    void PythonBindings::Shutdown()
    {
        m_impl->initialized = false;
    }

    bool PythonBindings::ExecuteCommand(const QString& command, const QStringList& args, QString& output) const
    {
        if (!m_impl->initialized)
        {
            output = "Python not initialized";
            return false;
        }

        QStringList fullArgs;
        fullArgs << "-m" << "o3de_pilot" << command << args;

        QProcess process;
        process.setWorkingDirectory(QDir(m_impl->cliModulePath).absolutePath());
        process.start(m_impl->pythonPath, fullArgs);
        process.waitForFinished(30000); // 30 second timeout

        output = process.readAllStandardOutput();
        QString errorOutput = process.readAllStandardError();

        if (!errorOutput.isEmpty())
        {
            qWarning() << "Python stderr:" << errorOutput;
        }

        return process.exitCode() == 0;
    }

    QStringList PythonBindings::GetProjects() const
    {
        QString output;
        if (ExecuteCommand("list", {"projects", "--json"}, output))
        {
            // TODO: Parse JSON output
            return QStringList();
        }
        return QStringList();
    }

    bool PythonBindings::CreateProject(const QString& name, const QString& path, const QString& templateName)
    {
        QString output;
        QStringList args = {name, "--path", path};
        if (!templateName.isEmpty())
        {
            args << "--template" << templateName;
        }
        return ExecuteCommand("init", args, output);
    }

    bool PythonBindings::OpenProject(const QString& path)
    {
        QString output;
        return ExecuteCommand("open", {path}, output);
    }

    bool PythonBindings::BuildProject(const QString& path)
    {
        QString output;
        return ExecuteCommand("build", {"--path", path}, output);
    }

    QStringList PythonBindings::GetInstalledGems() const
    {
        QString output;
        if (ExecuteCommand("list", {"gems", "--json"}, output))
        {
            // TODO: Parse JSON output
            return QStringList();
        }
        return QStringList();
    }

    QStringList PythonBindings::SearchGems(const QString& query) const
    {
        QString output;
        if (ExecuteCommand("search", {query, "--type", "gem", "--json"}, output))
        {
            // TODO: Parse JSON output
            return QStringList();
        }
        return QStringList();
    }

    bool PythonBindings::InstallGem(const QString& gemName)
    {
        QString output;
        return ExecuteCommand("install", {gemName}, output);
    }

    bool PythonBindings::UninstallGem(const QString& gemName)
    {
        QString output;
        return ExecuteCommand("uninstall", {gemName}, output);
    }

    QStringList PythonBindings::GetTemplates() const
    {
        QString output;
        if (ExecuteCommand("list", {"templates", "--json"}, output))
        {
            // TODO: Parse JSON output
            return QStringList();
        }
        return QStringList();
    }

    QStringList PythonBindings::GetRegisteredEngines() const
    {
        QString output;
        if (ExecuteCommand("list", {"engines", "--json"}, output))
        {
            // TODO: Parse JSON output
            return QStringList();
        }
        return QStringList();
    }

    QString PythonBindings::AskAI(const QString& prompt) const
    {
        QString output;
        if (ExecuteCommand("ai", {"ask", prompt}, output))
        {
            return output;
        }
        return QString();
    }

    bool PythonBindings::ConfigureAIProvider(const QString& provider, const QString& apiKey)
    {
        QString output;
        return ExecuteCommand("config", {"set", "ai.provider", provider}, output) &&
               ExecuteCommand("config", {"set", "ai.api_key", apiKey}, output);
    }

    QStringList PythonBindings::SearchRegistry(const QString& query) const
    {
        QString output;
        if (ExecuteCommand("search", {query, "--json"}, output))
        {
            // TODO: Parse JSON output
            return QStringList();
        }
        return QStringList();
    }

    void PythonBindings::ExecuteAsync(const QString& command, const QStringList& args, ResultCallback callback)
    {
        // Run in separate thread
        QThread* thread = QThread::create([this, command, args, callback]() {
            QString output;
            bool success = ExecuteCommand(command, args, output);
            callback(success, QVariant(output));
        });
        thread->start();
    }

} // namespace O3DEPilot
