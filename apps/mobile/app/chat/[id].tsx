import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Animated,
  Easing,
  FlatList,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import { Audio } from "expo-av";
import { useAuth } from "../../src/context/AuthContext";
import { useChat, type ChatMessage } from "../../src/hooks/useChat";
import { apiClient } from "../../src/api/client";
import { ENDPOINTS } from "../../src/api/endpoints";

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <View className={`px-4 py-1 ${isUser ? "items-end" : "items-start"}`}>
      <View
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
          isUser ? "bg-brand rounded-tr-sm" : "bg-zinc-800 rounded-tl-sm"
        }`}
      >
        <Text className="text-white text-base leading-relaxed">{msg.text}</Text>
      </View>
    </View>
  );
}

function ThinkingDots() {
  const dot0 = useRef(new Animated.Value(0)).current;
  const dot1 = useRef(new Animated.Value(0)).current;
  const dot2 = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const pulse = (val: Animated.Value, startDelay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(startDelay),
          Animated.timing(val, { toValue: 1, duration: 300, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
          Animated.timing(val, { toValue: 0, duration: 300, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
          Animated.delay(400 - startDelay),
        ])
      );

    const anims = [pulse(dot0, 0), pulse(dot1, 133), pulse(dot2, 266)];
    anims.forEach((a) => a.start());
    return () => anims.forEach((a) => a.stop());
  }, []);

  const dotStyle = (val: Animated.Value) => ({
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: "#a1a1aa",
    opacity: val.interpolate({ inputRange: [0, 1], outputRange: [0.25, 1] }),
    transform: [{ scale: val.interpolate({ inputRange: [0, 1], outputRange: [0.75, 1.15] }) }],
  });

  return (
    <View style={{ flexDirection: "row", gap: 5, alignItems: "center", paddingVertical: 4 }}>
      <Animated.View style={dotStyle(dot0)} />
      <Animated.View style={dotStyle(dot1)} />
      <Animated.View style={dotStyle(dot2)} />
    </View>
  );
}

function StreamingBubble({ text }: { text: string }) {
  return (
    <View className="px-4 py-1 items-start">
      <View className="max-w-[80%] rounded-2xl rounded-tl-sm bg-zinc-800 px-4 py-2.5">
        {text ? (
          <Text className="text-white text-base leading-relaxed">{text}</Text>
        ) : (
          <ThinkingDots />
        )}
      </View>
    </View>
  );
}

export default function ChatScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { ownerId, accessToken } = useAuth();
  const insets = useSafeAreaInsets();
  const [inputText, setInputText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const pendingAudioUri = useRef<string | null>(null);
  const flatListRef = useRef<FlatList>(null);
  const isNearBottomRef = useRef(true);

  const { messages, streamingText, connectionState, degraded, connect, disconnect, sendMessage } =
    useChat(ownerId ?? "", accessToken ?? "", id === "new" ? undefined : id);

  useEffect(() => {
    if (ownerId && accessToken) connect();
    return () => disconnect();
  }, [ownerId, accessToken]);

  useEffect(() => {
    if (isNearBottomRef.current) {
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
    }
  }, [messages.length, !!streamingText]);

  const handleSend = async () => {
    if (isRecording && recording) {
      // Step 1: stop → transcribe → fill input for review
      setIsRecording(false);
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      setRecording(null);
      if (!uri) return;
      pendingAudioUri.current = uri;
      setTranscribing(true);
      try {
        const form = new FormData();
        form.append("file", { uri, name: "voice.m4a", type: "audio/m4a" } as any);
        const { data } = await apiClient.post<{ text: string }>(
          ENDPOINTS.KNOWLEDGE_TRANSCRIBE,
          form,
          { headers: { "Content-Type": "multipart/form-data" }, timeout: 120_000 }
        );
        const transcribed = data.text?.trim();
        if (transcribed) {
          setInputText(transcribed);
        } else {
          Alert.alert("Nothing transcribed", "No speech was detected.");
        }
      } catch (e: any) {
        const detail =
          e?.response?.data?.error?.message ??
          e?.response?.data?.detail ??
          e?.message ??
          "Unknown error";
        Alert.alert("Transcription failed", detail);
        pendingAudioUri.current = null;
      } finally {
        setTranscribing(false);
      }
      return;
    }

    // Step 2 (or plain text): send to chat + upload pending audio
    if (!inputText.trim()) return;
    sendMessage(inputText);
    setInputText("");

    if (pendingAudioUri.current) {
      const uri = pendingAudioUri.current;
      pendingAudioUri.current = null;
      const audioForm = new FormData();
      audioForm.append("file", { uri, name: "voice.m4a", type: "audio/m4a" } as any);
      apiClient.post(ENDPOINTS.KNOWLEDGE_INGEST_AUDIO, audioForm, {
        headers: { "Content-Type": "multipart/form-data" },
      }).catch(() => {});
    }
  };

  const handleFilePick = async () => {
    Keyboard.dismiss();
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ["application/pdf", "text/*", "application/msword",
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        copyToCacheDirectory: true,
      });
      if (result.canceled || !result.assets[0]) return;
      const file = result.assets[0];
      setUploading(true);
      const form = new FormData();
      form.append("file", { uri: file.uri, name: file.name, type: file.mimeType ?? "application/octet-stream" } as any);
      await apiClient.post(ENDPOINTS.KNOWLEDGE_INGEST_DOCUMENT, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      Alert.alert("Uploaded", `"${file.name}" added to knowledge base.`);
    } catch (e: any) {
      Alert.alert("Upload failed", (e as any)?.message ?? "Unknown error");
    } finally {
      setUploading(false);
    }
  };

  const handleImagePick = async () => {
    Keyboard.dismiss();
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) { Alert.alert("Permission required", "Allow photo library access to send images."); return; }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.All,
      quality: 0.85,
      videoMaxDuration: 300,
    });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    setUploading(true);
    try {
      const form = new FormData();
      const isVideo = asset.type === "video";
      const name = asset.fileName ?? (isVideo ? "video.mp4" : "image.jpg");
      const mime = isVideo ? "video/mp4" : "image/jpeg";
      form.append("file", { uri: asset.uri, name, type: mime } as any);
      const endpoint = isVideo ? ENDPOINTS.KNOWLEDGE_INGEST_VIDEO : ENDPOINTS.KNOWLEDGE_INGEST_IMAGE;
      await apiClient.post(endpoint, form, { headers: { "Content-Type": "multipart/form-data" } });
      Alert.alert("Uploaded", `${isVideo ? "Video" : "Photo"} added to knowledge base.`);
    } catch (e: any) {
      Alert.alert("Upload failed", e?.message ?? "Unknown error");
    } finally {
      setUploading(false);
    }
  };

  const handleCameraPhoto = async () => {
    Keyboard.dismiss();
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) { Alert.alert("Permission required", "Allow camera access to take photos."); return; }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    setUploading(true);
    try {
      const form = new FormData();
      const name = asset.fileName ?? "photo.jpg";
      form.append("file", { uri: asset.uri, name, type: "image/jpeg" } as any);
      await apiClient.post(ENDPOINTS.KNOWLEDGE_INGEST_IMAGE, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      Alert.alert("Uploaded", "Photo added to knowledge base.");
    } catch (e: any) {
      Alert.alert("Upload failed", e?.message ?? "Unknown error");
    } finally {
      setUploading(false);
    }
  };

  const handleVoiceToggle = async () => {
    Keyboard.dismiss();
    if (isRecording) {
      // Cancel — stop without sending
      setIsRecording(false);
      if (recording) {
        await recording.stopAndUnloadAsync();
        setRecording(null);
      }
      setInputText("");
      return;
    }
    const perm = await Audio.requestPermissionsAsync();
    if (!perm.granted) { Alert.alert("Permission required", "Allow microphone access to record."); return; }
    await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
    const { recording: rec } = await Audio.Recording.createAsync(
      Audio.RecordingOptionsPresets.HIGH_QUALITY
    );
    setRecording(rec);
    setIsRecording(true);
  };

  const handleVideoCall = () => {
    Keyboard.dismiss();
    Alert.alert("Video Call", "Video calls require the full native app. Feature coming soon.");
  };

  const handleVideoRecord = async () => {
    Keyboard.dismiss();
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) { Alert.alert("Permission required", "Allow camera access to record video."); return; }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Videos,
      videoMaxDuration: 120,
      quality: 0.8,
    });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", { uri: asset.uri, name: "recording.mp4", type: "video/mp4" } as any);
      await apiClient.post(ENDPOINTS.KNOWLEDGE_INGEST_VIDEO, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      Alert.alert("Uploaded", "Video added to knowledge base.");
    } catch (e: any) {
      Alert.alert("Upload failed", e?.message ?? "Unknown error");
    } finally {
      setUploading(false);
    }
  };

  const statusColor =
    connectionState === "connected"
      ? "#22c55e"
      : connectionState === "connecting"
      ? "#f59e0b"
      : "#ef4444";

  const isStreaming = streamingText.length > 0;
  const canSend = connectionState === "connected" && !isStreaming && !uploading && !transcribing;
  const canSendNow = canSend && (!!inputText.trim() || isRecording);

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={{ flex: 1, backgroundColor: "#000" }}
    >
      <SafeAreaView style={{ flex: 1 }} edges={["top", "left", "right"]}>
        {/* Header */}
        <View className="flex-row items-center px-4 py-3 border-b border-zinc-900 gap-3">
          <Pressable onPress={() => router.back()} className="active:opacity-60">
            <Ionicons name="arrow-back" size={24} color="#fff" />
          </Pressable>
          <View className="flex-1">
            <Text className="text-white font-semibold text-lg">Chat</Text>
            <View className="flex-row items-center gap-1.5">
              <View className="w-2 h-2 rounded-full" style={{ backgroundColor: statusColor }} />
              <Text className="text-zinc-500 text-xs capitalize">{connectionState}</Text>
            </View>
          </View>
          {(connectionState === "disconnected" || connectionState === "error") && (
            <Pressable onPress={connect} className="active:opacity-60">
              <Ionicons name="refresh" size={20} color="#6366f1" />
            </Pressable>
          )}
        </View>

        {/* Degraded warning */}
        {degraded && (
          <View className="bg-amber-900/40 border-b border-amber-800 px-4 py-2">
            <Text className="text-amber-300 text-xs">
              Knowledge search unavailable — responses may be less accurate.
            </Text>
          </View>
        )}

        {/* Messages */}
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={(m) => m.id}
          keyboardDismissMode="on-drag"
          keyboardShouldPersistTaps="handled"
          style={{ flex: 1 }}
          contentContainerStyle={{ paddingVertical: 12, gap: 4 }}
          onScroll={({ nativeEvent: { contentOffset, contentSize, layoutMeasurement } }) => {
            const distanceFromBottom = contentSize.height - layoutMeasurement.height - contentOffset.y;
            isNearBottomRef.current = distanceFromBottom < 80;
          }}
          scrollEventThrottle={100}
          ListEmptyComponent={
            !isStreaming ? (
              <View className="items-center justify-center py-20 gap-2">
                <Ionicons name="chatbubble-outline" size={36} color="#3f3f46" />
                <Text className="text-zinc-500 text-sm">Say something to start</Text>
              </View>
            ) : null
          }
          ListFooterComponent={isStreaming ? <StreamingBubble text={streamingText} /> : null}
          renderItem={({ item }) => <MessageBubble msg={item} />}
        />

        {/* Input bar */}
        <View
          style={{ paddingBottom: insets.bottom || 8 }}
          className="border-t border-zinc-900 px-3 pt-2 bg-black"
        >
          {/* Action row */}
          <View className="flex-row items-center gap-2 pb-2">
            <Pressable
              onPress={handleFilePick}
              disabled={uploading}
              className="w-8 h-8 items-center justify-center active:opacity-60 disabled:opacity-40"
            >
              {uploading ? (
                <ActivityIndicator size="small" color="#6366f1" />
              ) : (
                <Ionicons name="attach" size={20} color="#71717a" />
              )}
            </Pressable>
            <Pressable
              onPress={handleImagePick}
              disabled={uploading}
              className="w-8 h-8 items-center justify-center active:opacity-60 disabled:opacity-40"
            >
              <Ionicons name="image-outline" size={20} color="#71717a" />
            </Pressable>
            <Pressable
              onPress={handleCameraPhoto}
              disabled={uploading}
              className="w-8 h-8 items-center justify-center active:opacity-60 disabled:opacity-40"
            >
              <Ionicons name="camera-outline" size={20} color="#71717a" />
            </Pressable>
            <Pressable
              onPress={handleVoiceToggle}
              disabled={uploading && !isRecording}
              className="w-8 h-8 items-center justify-center active:opacity-60 disabled:opacity-40"
            >
              <Ionicons
                name={isRecording ? "close-circle" : "mic-outline"}
                size={20}
                color={isRecording ? "#ef4444" : "#71717a"}
              />
            </Pressable>
            <Pressable
              onPress={handleVideoCall}
              className="w-8 h-8 items-center justify-center active:opacity-60"
            >
              <Ionicons name="videocam-outline" size={20} color="#71717a" />
            </Pressable>
            <Pressable
              onPress={handleVideoRecord}
              disabled={uploading}
              className="w-8 h-8 items-center justify-center active:opacity-60 disabled:opacity-40"
            >
              <Ionicons name="film-outline" size={20} color="#71717a" />
            </Pressable>
          </View>

          {/* Text + send row */}
          <View className="flex-row items-end gap-2">
            <View style={{ flex: 1, position: "relative" }}>
              {(isRecording || transcribing) && (
                <View style={{ position: "absolute", right: 12, top: 12, zIndex: 1, flexDirection: "row", alignItems: "center", gap: 4 }}>
                  {transcribing
                    ? <ActivityIndicator size="small" color="#6366f1" />
                    : <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: "#ef4444" }} />
                  }
                  <Text style={{ color: transcribing ? "#6366f1" : "#ef4444", fontSize: 11 }}>
                    {transcribing ? "Transcribing…" : "Listening…"}
                  </Text>
                </View>
              )}
              <TextInput
                className="bg-zinc-900 text-white rounded-2xl px-4 py-3 border border-zinc-800 max-h-28"
                placeholder={isRecording ? "Speak now… (tap ↑ to transcribe)" : "Message…"}
                placeholderTextColor={isRecording ? "#ef4444" : "#71717a"}
                value={inputText}
                onChangeText={setInputText}
                multiline
                returnKeyType="send"
                onSubmitEditing={handleSend}
                blurOnSubmit={false}
                editable={canSend && !isRecording}
              />
            </View>
            <Pressable
              onPress={handleSend}
              disabled={!canSendNow}
              className="bg-brand rounded-full w-11 h-11 items-center justify-center active:opacity-70 disabled:opacity-40"
            >
              {transcribing
                ? <ActivityIndicator size="small" color="#fff" />
                : <Ionicons name="arrow-up" size={20} color="#fff" />
              }
            </Pressable>
          </View>
        </View>
      </SafeAreaView>
    </KeyboardAvoidingView>
  );
}
