qt_add_qml_module(caelestia-blobs
    URI Caelestia.Blobs
    VERSION 1.0
    SOURCES
        blobgroup.cpp blobgroup.hpp
        blobshape.cpp blobshape.hpp
        blobrect.cpp blobrect.hpp
        blobinvertedrect.cpp blobinvertedrect.hpp
        blobmaterial.cpp blobmaterial.hpp
)

target_link_libraries(caelestia-blobs PRIVATE Qt6::Core Qt6::Gui Qt6::Qml Qt6::Quick)
target_include_directories(caelestia-blobs PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
set_target_properties(caelestia-blobs PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${QT_QML_OUTPUT_DIRECTORY}/Caelestia/Blobs"
)
set_target_properties(caelestia-blobsplugin PROPERTIES
    BUILD_RPATH "$ORIGIN"
)

qt_add_shaders(caelestia-blobs "blob_shaders"
    BATCHABLE OPTIMIZED NOHLSL NOMSL
    GLSL "300es,330"
    PREFIX "/"
    FILES
        shaders/blob.frag
        shaders/blob.vert
)
