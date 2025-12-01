use std::env;
use std::path::PathBuf;

fn main() {
    // 1. Get the directory of the canSDK
    let sdk_dir = PathBuf::from("canSDK");

    // Get the libusb paths using pkg-config
    let libusb = pkg_config::probe_library("libusb-1.0").expect("libusb-1.0 not found. Please install it.");
    let libusb_include_path = &libusb.include_paths[0];

    // 2. Use the `cc` crate to compile the C++ source files
    cc::Build::new()
        .cpp(true) // Enable C++ compilation
        .file(sdk_dir.join("src/c_wrapper.cpp"))
        // .file(sdk_dir.join("src/protocol/damiao.cpp"))
        .include(sdk_dir.join("include"))
        .include(libusb_include_path) // Add libusb include path
        .flag("-std=c++14") // Match the standard from CMake
        .compile("can_sdk_wrapper"); // Output library name

    // 3. Link against the precompiled static library and libusb
    println!("cargo:rustc-link-search=native={}", sdk_dir.join("lib").display());
    println!("cargo:rustc-link-lib=static=u2canfd");
    for lib in &libusb.libs {
        println!("cargo:rustc-link-lib={}", lib);
    }
    
    println!("cargo:rerun-if-changed=canSDK/include/protocol/usb_class.h");
    println!("cargo:rerun-if-changed=canSDK/src/c_wrapper.h");
    println!("cargo:rerun-if-changed=canSDK/src/c_wrapper.cpp");
    // println!("cargo:rerun-if-changed=canSDK/src/protocol/damiao.cpp");


    let mingw = "C:/msys64/mingw64";

    println!("cargo:rustc-env=BINDGEN_EXTRA_CLANG_ARGS=-I{}/include -I{}/include/c++/15.2.0 -I{}/include/c++/15.2.0/x86_64-w64-mingw32",
    mingw, mingw, mingw);

    // 4. Use bindgen to generate the Rust bindings
    let bindings = bindgen::Builder::default()
        .clang_arg("-target")
        .clang_arg("x86_64-w64-mingw32")
        .clang_arg("-I")
        .clang_arg("C:/msys64/mingw64/include")
        .clang_arg("-I")
        .clang_arg("C:/msys64/mingw64/x86_64-w64-mingw32/include")
        .clang_arg("-fno-ms-compatibility")
        //.header(sdk_dir.join("src/c_wrapper.h").to_str().unwrap())
        .header("canSDK/src/c_wrapper.h")
        // Pass the include path for usb_class.h
        .clang_arg(format!("-I{}", sdk_dir.join("include").display()))
        .clang_arg(format!("-I{}", libusb_include_path.display()))
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::new()))
        .generate()
        .expect("Unable to generate bindings");

    // 5. Write the bindings to the $OUT_DIR/bindings.rs file.
    let out_path = PathBuf::from(env::var("OUT_DIR").unwrap());
    bindings
        .write_to_file(out_path.join("bindings.rs"))
        .expect("Couldn't write bindings!");
}
