# Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved
cmake_minimum_required (VERSION 2.6)
project (ion-dbreports)
set(PROJECT_DESCRIPTION "Ion Torrent Browser")
enable_testing()

include(../buildTools/cmake/CMakeLists.version.txt)
include(../buildTools/cmake/CMakeLists.compiler.txt)

FIND_PACKAGE(PythonInterp)
# Determine python site-packages or dist-packages directory
execute_process (
        COMMAND "${PYTHON_EXECUTABLE}" -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"
        OUTPUT_VARIABLE PYTHON_SITE_PACKAGES
        OUTPUT_STRIP_TRAILING_WHITESPACE
)
# NOTE: still used in postinst to purge files that used to be installed here
execute_process (
        COMMAND "${PYTHON_EXECUTABLE}" -c "from distutils.sysconfig import get_python_lib; print get_python_lib(prefix='/usr/local')"
        OUTPUT_VARIABLE PYTHON_LOCAL_SITE_PACKAGES
        OUTPUT_STRIP_TRAILING_WHITESPACE
)
execute_process (
        COMMAND "${PYTHON_EXECUTABLE}" -c "from distutils.sysconfig import get_python_version; print get_python_version()"
        OUTPUT_VARIABLE PYTHON_VERSION
        OUTPUT_STRIP_TRAILING_WHITESPACE
)

# Where to install - override with: -DION_INSTALL_PREFIX
set(ION_INSTALL_PREFIX "/opt/ion" CACHE PATH "Ion Install Prefix")
set(CMAKE_INSTALL_PREFIX "${ION_INSTALL_PREFIX}" CACHE INTERNAL "Prefix prepended to install directories" FORCE)
set(CPACK_PACKAGING_INSTALL_PREFIX ${ION_INSTALL_PREFIX})
set(CPACK_SET_DESTDIR "ON")

configure_file (
	"${PROJECT_SOURCE_DIR}/debian/postinst.in"
	"${PROJECT_BINARY_DIR}/debian/postinst" @ONLY
)
configure_file (
	"${PROJECT_SOURCE_DIR}/debian/postrm.in"
	"${PROJECT_BINARY_DIR}/debian/postrm" @ONLY
)
configure_file (
	"${PROJECT_SOURCE_DIR}/debian/preinst.in"
	"${PROJECT_BINARY_DIR}/debian/preinst" @ONLY
)
configure_file (
	"${PROJECT_SOURCE_DIR}/debian/prerm.in"
	"${PROJECT_BINARY_DIR}/debian/prerm" @ONLY
)

add_custom_target(compileall ALL
    COMMAND ${PYTHON_EXECUTABLE} -m compileall -q -f "${PROJECT_SOURCE_DIR}/iondb/"
)

install(FILES "${PROJECT_SOURCE_DIR}/../buildTools/terms-of-use.txt" DESTINATION /var/www/licenses)
install(FILES "${PROJECT_SOURCE_DIR}/iondb/media/TorrentServerSplash.jpg" DESTINATION /var/www)
install(FILES "${PROJECT_SOURCE_DIR}/iondb/media/favicon.ico" DESTINATION /var/www)
install(FILES "${PROJECT_SOURCE_DIR}/iondb/index.html" DESTINATION /var/www)
install(FILES "${PROJECT_SOURCE_DIR}/iondb/docsnotfound.html" DESTINATION /var/www)
    
install(DIRECTORY iondb DESTINATION .
    USE_SOURCE_PERMISSIONS
    PATTERN "local_settings.py" EXCLUDE
    PATTERN ".svn" EXCLUDE
    PATTERN "rndbin" EXCLUDE
    PATTERN "ionArchive" EXCLUDE
    PATTERN "ionCrawler" EXCLUDE
    PATTERN "ionJobServer" EXCLUDE
    PATTERN "ionPlugin" EXCLUDE
    PATTERN "media/TorrentServerSplash.jpg" EXCLUDE
    PATTERN "media/favicon.ico" EXCLUDE
    PATTERN "iondb/media/resources/kendo/examples/" EXCLUDE
    PATTERN "iondb/media/resources/kendo/source/" EXCLUDE
    PATTERN "iondb/media/resources/bootstrap/less/" EXCLUDE
    PATTERN "*.less" EXCLUDE
    PATTERN "iondb/index.html" EXCLUDE
    PATTERN "iondb/docsnotfound.html" EXCLUDE
    PATTERN "iondb/wsgi/iontorrent.conf.in" EXCLUDE
    PATTERN "iondb/wsgi/torrent-server.in" EXCLUDE
    PATTERN "iondb/wsgi/torrent-server-ssl.in" EXCLUDE
    PATTERN "*.pyc" EXCLUDE
    PATTERN "*.pyo" EXCLUDE
)
install(PROGRAMS iondb/bin/ionArchive DESTINATION /etc/init.d)
install(PROGRAMS iondb/bin/ionCrawler DESTINATION /etc/init.d)
install(PROGRAMS iondb/bin/ionJobServer DESTINATION /etc/init.d)
install(PROGRAMS iondb/bin/ionPlugin DESTINATION /etc/init.d)
install(PROGRAMS iondb/bin/celeryd DESTINATION /etc/init.d)
install(PROGRAMS iondb/bin/celery.conf DESTINATION config)

configure_file (
    "${PROJECT_SOURCE_DIR}/iondb/wsgi/torrent-server.in"
    "${PROJECT_BINARY_DIR}/apache2/torrent-server" @ONLY
)
install(FILES "${PROJECT_BINARY_DIR}/apache2/torrent-server" DESTINATION /etc/apache2/sites-available)

configure_file (
    "${PROJECT_SOURCE_DIR}/iondb/wsgi/torrent-server-ssl.in"
    "${PROJECT_BINARY_DIR}/apache2/torrent-server-ssl.example" @ONLY
)
install(FILES "${PROJECT_BINARY_DIR}/apache2/torrent-server-ssl.example" DESTINATION /etc/apache2/sites-available)

# Add ION_INSTALL_PREFIX to system python path so iondb modules can be found
file(WRITE ${PROJECT_BINARY_DIR}/iondb.pth "${ION_INSTALL_PREFIX}\n")
install(FILES ${PROJECT_BINARY_DIR}/iondb.pth DESTINATION ${PYTHON_SITE_PACKAGES})

configure_file (
	"${PROJECT_SOURCE_DIR}/../buildTools/IonVersion.py.in"
	"${PROJECT_BINARY_DIR}/IonTorrent/IonVersion.py" @ONLY
)
install(FILES "${PROJECT_BINARY_DIR}/IonTorrent/IonVersion.py" DESTINATION iondb
    RENAME version.py
)

include(InstallRequiredSystemLibraries)
set(CPACK_GENERATOR "DEB")

include(../buildTools/cmake/CMakeLists.cpack.txt)

#% nice to automate this
set(CPACK_DEBIAN_PACKAGE_DEPENDS "python,
    ion-pipeline (>= 3.0.2),
    zeroinstall-injector (>= 1.5),
    postgresql,
    php5,
    libapache2-mod-wsgi,
    python-celery (>= 2.4.0),
    python-django (>= 1.4),
    python-django-celery,
    python-django-south (>=0.7.3),
	python-matplotlib,
	python-scipy,
	python-psycopg2, 
	python-twisted-core, 
	python-central, 
	python-twisted, 
	python-support,
	python-lxml,
	python-docutils,
    python-setuptools,
    python-httplib2,
    python-dateutil,
    python-argparse,
    python-tastypie (>= 0.9.11+ion1),
	python-drmaa,
    samtools (>= 0.1.18),
    python-dev,
  rabbitmq-server,
  tmap (>=0.3.7)")

# Incompatible with older tastypie, remove or upgrade before installing
set(CPACK_DEBIAN_PACKAGE_BREAKS "python-tastypie (<= 0.9.10)")
# If updating from a really old version of tastypie, make sure it is
# removed/upgraded prior to this (or postinst fails)
set(CPACK_DEBIAN_PACKAGE_CONFLICTS "python-django-tastypie")

set(CPACK_PACKAGE_DESCRIPTION "This package contains the Torrent Browser and related programs including the job crawler, and the archive daemon.")
set(CPACK_DEBIAN_PACKAGE_CONTROL_EXTRA
	${CMAKE_CURRENT_BINARY_DIR}/debian/postinst
	${CMAKE_CURRENT_BINARY_DIR}/debian/prerm
	${CMAKE_CURRENT_BINARY_DIR}/debian/postrm
	${CMAKE_CURRENT_BINARY_DIR}/debian/triggers
)
include(CPack)
