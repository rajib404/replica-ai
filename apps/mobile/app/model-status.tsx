import { useQuery } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { apiClient } from "../src/api/client";
import { ENDPOINTS } from "../src/api/endpoints";

interface ModelStatus {
  model_name?: string;
  provider?: string;
  status?: string;
  version?: string;
  parameters?: string;
  context_length?: number;
  created_at?: string;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View className="px-4 py-3.5">
      <Text className="text-zinc-500 text-xs mb-1">{label}</Text>
      <Text className="text-white text-sm font-medium">{value}</Text>
    </View>
  );
}

function Divider() {
  return <View className="h-px bg-zinc-800 ml-4" />;
}

export default function ModelStatusScreen() {
  const router = useRouter();

  const { data, isLoading, error } = useQuery<ModelStatus>({
    queryKey: ["model-status"],
    queryFn: async () => {
      const { data } = await apiClient.get(ENDPOINTS.MODEL_STATUS);
      return data;
    },
    retry: 1,
  });

  return (
    <SafeAreaView className="flex-1 bg-black" edges={["top", "left", "right"]}>
      <View className="flex-row items-center gap-3 px-4 py-3 border-b border-zinc-900">
        <Pressable onPress={() => router.back()} className="active:opacity-60">
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </Pressable>
        <Text className="text-white font-semibold text-lg flex-1">Model Status</Text>
      </View>

      {isLoading ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator color="#6366f1" />
        </View>
      ) : error || !data ? (
        <View className="flex-1 items-center justify-center gap-3 px-8">
          <Ionicons name="server-outline" size={48} color="#3f3f46" />
          <Text className="text-zinc-400 text-center">Model status unavailable</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 32, gap: 16 }}>
          <View className="bg-zinc-900 rounded-2xl border border-zinc-800 overflow-hidden">
            {data.model_name && <Row label="Model" value={data.model_name} />}
            {data.provider && (
              <>
                <Divider />
                <Row label="Provider" value={data.provider} />
              </>
            )}
            {data.status && (
              <>
                <Divider />
                <View className="px-4 py-3.5 flex-row items-center gap-2">
                  <View
                    className="w-2 h-2 rounded-full"
                    style={{
                      backgroundColor:
                        data.status === "ready" || data.status === "running"
                          ? "#22c55e"
                          : "#f59e0b",
                    }}
                  />
                  <Text className="text-white text-sm capitalize">{data.status}</Text>
                </View>
              </>
            )}
            {data.version && (
              <>
                <Divider />
                <Row label="Version" value={data.version} />
              </>
            )}
            {data.parameters && (
              <>
                <Divider />
                <Row label="Parameters" value={data.parameters} />
              </>
            )}
            {data.context_length && (
              <>
                <Divider />
                <Row label="Context length" value={`${data.context_length.toLocaleString()} tokens`} />
              </>
            )}
          </View>

          {data.created_at && (
            <Text className="text-zinc-600 text-xs text-center">
              Model created {new Date(data.created_at).toLocaleDateString()}
            </Text>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
