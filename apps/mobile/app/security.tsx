import { useState } from "react";
import {
  Alert,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { apiClient } from "../src/api/client";
import { ENDPOINTS } from "../src/api/endpoints";

function SectionHeader({ title }: { title: string }) {
  return (
    <Text className="text-zinc-500 text-xs font-semibold uppercase tracking-wider px-1 mb-2">
      {title}
    </Text>
  );
}

function ActionRow({
  icon,
  label,
  description,
  onPress,
  destructive,
}: {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  description?: string;
  onPress: () => void;
  destructive?: boolean;
}) {
  const color = destructive ? "#ef4444" : "#6366f1";
  return (
    <Pressable
      onPress={onPress}
      className="flex-row items-center gap-3 px-4 py-4 active:bg-zinc-800/50"
    >
      <View
        className="w-9 h-9 rounded-xl items-center justify-center"
        style={{ backgroundColor: color + "22" }}
      >
        <Ionicons name={icon} size={18} color={color} />
      </View>
      <View className="flex-1">
        <Text className={`font-medium ${destructive ? "text-red-400" : "text-white"}`}>{label}</Text>
        {description && (
          <Text className="text-zinc-500 text-xs">{description}</Text>
        )}
      </View>
      <Ionicons name="chevron-forward" size={15} color="#52525b" />
    </Pressable>
  );
}

function Divider() {
  return <View className="h-px bg-zinc-800 ml-14" />;
}

export default function SecurityScreen() {
  const router = useRouter();

  const handleSetup2FA = async () => {
    try {
      const { data } = await apiClient.post(ENDPOINTS.SECURITY_2FA_SETUP, {});
      Alert.alert(
        "2FA Setup",
        `Scan this secret in your authenticator app:\n\n${data.secret ?? "See web dashboard for QR code"}`,
        [{ text: "OK" }],
      );
    } catch {
      Alert.alert("Error", "Could not set up 2FA. Try from the web dashboard.");
    }
  };

  const handleExport = async () => {
    Alert.alert(
      "Export Data",
      "This will queue a data export. You'll receive a download link via the web dashboard.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Request Export",
          onPress: async () => {
            try {
              await apiClient.post(ENDPOINTS.SECURITY_EXPORT, {});
              Alert.alert("Export Requested", "Your data export is being prepared.");
            } catch {
              Alert.alert("Error", "Could not request export. Try from the web dashboard.");
            }
          },
        },
      ],
    );
  };

  const handleDeleteAccount = () => {
    Alert.alert(
      "Delete Account",
      "This is permanent and cannot be undone. All your data will be deleted.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Continue on Web",
          style: "destructive",
          onPress: () =>
            Alert.alert(
              "Use Web Dashboard",
              "For your safety, account deletion must be confirmed from the web dashboard.",
            ),
        },
      ],
    );
  };

  return (
    <SafeAreaView className="flex-1 bg-black" edges={["top", "left", "right"]}>
      <View className="flex-row items-center gap-3 px-4 py-3 border-b border-zinc-900">
        <Pressable onPress={() => router.back()} className="active:opacity-60">
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </Pressable>
        <Text className="text-white font-semibold text-lg flex-1">Security</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 20 }}>
        {/* Authentication */}
        <View>
          <SectionHeader title="Authentication" />
          <View className="bg-zinc-900 rounded-2xl border border-zinc-800 overflow-hidden">
            <ActionRow
              icon="key"
              label="Set up 2FA"
              description="Add two-factor authentication"
              onPress={handleSetup2FA}
            />
          </View>
        </View>

        {/* Data */}
        <View>
          <SectionHeader title="Your Data" />
          <View className="bg-zinc-900 rounded-2xl border border-zinc-800 overflow-hidden">
            <ActionRow
              icon="download"
              label="Export Data"
              description="Download all your data"
              onPress={handleExport}
            />
          </View>
        </View>

        {/* Danger zone */}
        <View>
          <SectionHeader title="Danger Zone" />
          <View className="bg-zinc-900 rounded-2xl border border-red-900/40 overflow-hidden">
            <ActionRow
              icon="trash"
              label="Delete Account"
              description="Permanently delete all data"
              onPress={handleDeleteAccount}
              destructive
            />
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
