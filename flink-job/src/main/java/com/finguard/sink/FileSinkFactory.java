package com.finguard.sink;

import org.apache.flink.api.common.serialization.SimpleStringEncoder;
import org.apache.flink.configuration.MemorySize;
import org.apache.flink.connector.file.sink.FileSink;
import org.apache.flink.core.fs.Path;
import org.apache.flink.streaming.api.functions.sink.filesystem.rollingpolicies.DefaultRollingPolicy;

import java.time.Duration;

public final class FileSinkFactory {
    private FileSinkFactory() {
    }

    public static FileSink<String> jsonLineSink(String outputPath) {
        return FileSink
                .forRowFormat(new Path(outputPath), new SimpleStringEncoder<String>("UTF-8"))
                .withRollingPolicy(DefaultRollingPolicy.builder()
                        .withRolloverInterval(Duration.ofMinutes(2))
                        .withInactivityInterval(Duration.ofSeconds(30))
                        .withMaxPartSize(MemorySize.ofMebiBytes(64))
                        .build())
                .build();
    }
}
