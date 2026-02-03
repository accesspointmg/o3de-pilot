/*
 * O3DE Pilot - AI-powered O3DE Project Manager
 * SPDX-License-Identifier: Apache-2.0 OR MIT
 */

#include "Application.h"
#include <QApplication>

int main(int argc, char* argv[])
{
    QApplication::setApplicationName("O3DE Pilot");
    QApplication::setOrganizationName("O3DE Foundation");
    QApplication::setApplicationVersion("0.1.0");

    O3DEPilot::Application app(argc, argv);
    return app.Run();
}
