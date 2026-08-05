package com.example.sdkdemo;

// Copyright (c) 2026 Bytedance, All rights reserved.

/**
 * app功能开关
 */
public class AppSettings {


    /**
     * 是否开启全面屏适配
     * 由于云手机Pod只能推1路视频流，开启此功能后Pod会按首个拉流的手机分辨率进行推流以实现全面屏适配，
     * 但此时如果有其他分辨率不同的手机也对此Pod进行拉流时，会造成其他手机视频流分辨率也是第一个手机的
     * 视频分辨率，可能产生预期外的显示效果，因此建议若存在多个终端对同一个云手机Pod拉流场景时，不要开
     * 启此功能
     */
    public static final boolean ENABLE_FULL_SCREEN = false;


    /**
     * 是否使用手机本地键盘进行文字输入交互，按业务需要进行配置即可
     * 默认是false，即使用云手机Pod内置输入法键盘进行文字输入
     */
    public static final boolean ENABLE_LOCAL_KEYBOARD = true;


    /**
     * 云手机Pod在推流过程会检测用户是否有操作，长时间不操作会自动停止推流
     * SDK默认的无操作自动回收时长是300s，这里功能演示配置为7200s，即2小时
     */
    public static final int AUTO_RECYCLE_TIME = 7200;

    /**
     * 是否自动启动veProxy
     */
   public static final boolean AUTO_START_VEPROXY = true;

    /**
     * 是否自动停止veProxy
     */
   public static final boolean AUTO_STOP_VEPROXY = true;
}
