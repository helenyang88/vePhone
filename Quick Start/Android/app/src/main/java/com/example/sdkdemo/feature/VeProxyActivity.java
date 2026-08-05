package com.example.sdkdemo.feature;


import android.os.Bundle;
import android.os.Handler;
import android.text.TextUtils;
import android.util.Log;
import android.view.WindowManager;
import android.widget.FrameLayout;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.example.sdkdemo.AppSettings;
import com.example.sdkdemo.InitApplication;
import com.example.sdkdemo.R;
import com.example.sdkdemo.base.BasePlayActivity;
import com.example.sdkdemo.util.CollectionUtil;
import com.example.sdkdemo.util.SdkUtil;
import com.volcengine.androidcloud.common.model.NetProxyParam;
import com.volcengine.androidcloud.common.model.PodProxyRequest;
import com.volcengine.cloudphone.apiservice.NetworkService;
import com.volcengine.phone.VePhoneEngine;
import com.volcengine.phone.veproxy.VeProxyClient;
import com.volcengine.phone.veproxy.api.InitParam;
import com.volcengine.phone.veproxy.api.ProxyProfile;
import com.volcengine.phone.veproxy.api.auth.AuthConfig;
import com.volcengine.phone.veproxy.api.auth.AuthMethod;
import com.volcengine.phone.veproxy.api.plugin.Socks5Plugin;
import com.volcengine.phone.veproxy.api.proxy.ProxyConfig;
import com.volcengine.phone.veproxy.api.proxy.ProxyTransport;
import com.volcengine.phone.veproxy.api.proxy.ProxyType;
import com.volcengine.phone.veproxy.api.transport.Tls;
import com.volcengine.phone.veproxy.api.transport.TransportConfig;
import com.volcengine.phone.veproxy.api.transport.TransportProtocol;

import java.text.MessageFormat;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class VeProxyActivity extends BasePlayActivity {
    private static final String TAG = "VeProxyActivity";
    private final List<Runnable> releaseTasks = new ArrayList<>();

    static {
        // 通常放在application#onCreate中初始化
        VeProxyClient.init(new InitParam.Builder(InitApplication.APP)
//                .notificationCreator(new MyNotificationCreator())
                .build());
    }


    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        FrameLayout container = new FrameLayout(this);
        container.setLayoutParams(new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(container);

        SdkUtil.checkPlayAuth(
                SdkUtil.getPlayAuth(this),
                p -> {
                    VePhoneEngine.getInstance().start(buildPhonePlayConfig(p, container), this);
                },
                p -> {
                    showTipDialog(MessageFormat.format(getString(R.string.invalid_phone_play_config) , p));
                });

        initVeProxy();
    }

    @Override
    protected void onResume() {
        super.onResume();
        VePhoneEngine.getInstance().resume();
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    @Override
    protected void onPause() {
        super.onPause();
        VePhoneEngine.getInstance().pause();
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    @Override
    protected void onDestroy() {
        uninitVeProxy();
        for (Runnable task : releaseTasks) {
            task.run();
        }
        if (releaseTasks.isEmpty()) {
            VePhoneEngine.getInstance().stop();
        } else {
            // 人为加延迟，确保取消service.setPodProxy解除Pod网络劫持
            new Handler().postDelayed(() -> VePhoneEngine.getInstance().stop(), 500);
        }
        super.onDestroy();
    }


    @Override
    public void onServiceInit(@NonNull Map<String, Object> extras) {
        NetworkService service = VePhoneEngine.getInstance().getNetworkService();
        if (service == null) {
            return;
        }
        if (!AppSettings.AUTO_START_VEPROXY) {
            return;
        }
        // 先检查目标代理服务是否已在运行中，防止重复启动
        // 启动分为两步：
        // 1. 开启pod网络流量劫持，即service.requestNetProxy接口，主要是防止这步重复调用影响pod网络稳定性
        // 2. 启动网络代理服务，即VeProxyClient.getInstance().start()接口，此接口内部做了防抖天然支持防止重复启动
        Set<ProxyProfile> activeProxies = VeProxyClient.getInstance().getActiveProxies();
        ProxyProfile target;
        String podId = SdkUtil.getPlayAuth(this).podId;
        if (!activeProxies.isEmpty() && (target = CollectionUtil.find(activeProxies, proxy -> TextUtils.equals(proxy.getProxies().get(0).getName(), podId))) != null) {
            showToast("当前已有匹配的代理在运行");
            Log.d(TAG, "onServiceInit: activeProxy:" + target);
            return;
        }

        service.requestNetProxy(new NetworkService.NetProxyListener() {
            @Override
            public void onSuccess(@NonNull NetProxyParam param) {
                ProxyProfile profile = createProxyProfileByParam(param);

                VeProxyClient.getInstance().start(VeProxyActivity.this, profile);

                // 退出拉流时，自动停止网络代理服务并关闭pod网络流量劫持
                if (AppSettings.AUTO_STOP_VEPROXY) {
                    releaseTasks.add(() -> {
                        // 1. 先关闭pod网络流量劫持
                        // 注意：这里建议调用云手机openapi来关闭，调用SDK的setPodProxy接口可能会失败，因为
                        // VePhoneEngine.getInstance().stop()接口会取消SDK内部所有的网络请求
                        service.setPodProxy(new PodProxyRequest.Builder().proxyStatus(PodProxyRequest.STATUS_OFF).build(), null);
                        // 2. 再停止网络代理服务
                        VeProxyClient.getInstance().stop(VeProxyActivity.this, profile);
                    });
                }
            }

            @Override
            public void onError(int code, @NonNull String msg) {
                // 开启pod网络重定向失败，一般是镜像版本太低不支持该功能，升级镜像版本即可
                showToast(MessageFormat.format("开启pod网络重定向失败，code:{0}, msg:{1}", code, msg));
                Log.d(TAG, "requestNetProxy#onError: code:" + code + ", msg:" + msg);
            }
        });
    }

    private ProxyProfile createProxyProfileByParam(@NonNull NetProxyParam param) {
        return new ProxyProfile.Builder()
                .stopProxyWhenDisconnected(false)
                .serverAddr(param.getServerHost())
                .serverPort(param.getServerPort())
                .auth(new AuthConfig.Builder().method(AuthMethod.TOKEN).token(param.getAuthToken()).build())
                .transport(
                        new TransportConfig.Builder()
                                .protocol(TransportProtocol.WSS)
                                .websocketPath(param.getServerFullPath())
                                .tls(new Tls.Builder()
                                        .certFile(param.getTlsClientCertPath())
                                        .keyFile(param.getTlsClientKeyPath())
                                        .trustedCaFile(param.getTlsServerCertPath())
                                        .serverName(param.getTlsServerName())
                                        .build())
                                .build()
                )
                .proxy(
                        new ProxyConfig.Builder()
                                .name(param.getPodId())  // 必须，固定写法
                                .type(ProxyType.TCP)  // also see: param.getProxyType()
                                .plugin(new Socks5Plugin())  //
                                .transport(
                                        new ProxyTransport.Builder()
                                                .bandwidthLimit("2MB")
                                                .useEncryption(true)
                                                .useCompression(true)
                                                .build()
                                )
                                .build()
                )
                .build();
    }

    private void initVeProxy() {
        VeProxyClient.getInstance()
                .setProxyLogListener((profile, message) -> {
                    // 监听网络代理服务日志
                    Log.d(TAG, "onLogMessage: " + message);
                })
                .setProxyStateListener((profile, state) -> {
                    List<String> list = CollectionUtil.map(profile.getProxies(), p -> p.getName() + "->" + profile.getServerAddr() + ":" + p.getRealRemotePort());
                    Log.w(TAG, "onProxyStateUpdated: " + list + ", state:" + state);
                });
    }

    private void uninitVeProxy() {
        VeProxyClient.getInstance()
                .setProxyLogListener(null)
                .setProxyStateListener(null);
    }
}
