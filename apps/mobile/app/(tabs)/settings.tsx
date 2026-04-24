import { useQuery } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../../src/context/AuthContext";
import { apiClient } from "../../src/api/client";
import { ENDPOINTS } from "../../src/api/endpoints";

interface BillingStatus {
  status: string;
  plan?: string;
  renewal_date?: string;
  survival_mode?: boolean;
}

interface ModelStatus {
  model_name: string;
  provider?: string;
  status?: string;
}

interface SettingsRowProps {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  value?: string;
  onPress?: () => void;
  destructive?: boolean;
  chevron?: boolean;
}

function SettingsRow({ icon, label, value, onPress, destructive, chevron }: SettingsRowProps) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      className={`flex-row items-center gap-3 px-4 py-4 ${onPress ? "active:bg-zinc-800/50" : ""}`}
    >
      <Ionicons name={icon} size={20} color={destructive ? "#f87171" : "#6366f1"} />
      <Text className={`flex-1 font-medium ${destructive ? "text-red-400" : "text-white"}`}>
        {label}
      </Text>
      {value ? <Text className="text-zinc-500 text-sm">{value}</Text> : null}
      {chevron ? <Ionicons name="chevron-forward" size={16} color="#52525b" /> : null}
    </Pressable>
  );
}

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <View className="bg-zinc-900 rounded-2xl border border-zinc-800 overflow-hidden mx-5">
      {children}
    </View>
  );
}

function Divider() {
  return <View className="h-px bg-zinc-800 ml-[52px]" />;
}

export default function SettingsTab() {
  const { ownerId, signOut } = useAuth();

  const { data: billing, isLoading: billingLoading } = useQuery<BillingStatus>({
    queryKey: ["billing"],
    queryFn: async () => {
      const { data } = await apiClient.get(ENDPOINTS.BILLING_STATUS);
      return data;
    },
    retry: false,
  });

  const { data: model } = useQuery<ModelStatus>({
    queryKey: ["model"],
    queryFn: async () => {
      const { data } = await apiClient.get(ENDPOINTS.MODEL_STATUS);
      return data;
    },
    retry: false,
  });

  const confirmSignOut = () => {
    Alert.alert("Sign out", "You'll need your owner ID and secret word to sign back in.", [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out", style: "destructive", onPress: signOut },
    ]);
  };

  return (
    <SafeAreaView className="flex-1 bg-black">
      <ScrollView contentContainerStyle={{ paddingBottom: 32 }}>
        <Text className="text-white text-2xl font-bold px-5 pb-4 pt-1">Settings</Text>

        {/* Account */}
        <View className="gap-2 mb-6">
          <Text className="text-zinc-500 text-xs font-medium uppercase tracking-wider px-5 mb-1">
            Account
          </Text>
          <SectionCard>
            <SettingsRow
              icon="finger-print"
              label="Owner ID"
              value={ownerId ? `${ownerId.slice(0, 8)}…` : "—"}
            />
          </SectionCard>
        </View>

        {/* AI */}
        <View className="gap-2 mb-6">
          <Text className="text-zinc-500 text-xs font-medium uppercase tracking-wider px-5 mb-1">
            AI
          </Text>
          <SectionCard>
            <SettingsRow
              icon="hardware-chip"
              label="Active model"
              value={model ? `${model.model_name}${model.provider ? ` · ${model.provider}` : ""}` : "—"}
            />
          </SectionCard>
        </View>

        {/* Billing */}
        <View className="gap-2 mb-6">
          <Text className="text-zinc-500 text-xs font-medium uppercase tracking-wider px-5 mb-1">
            Billing
          </Text>
          <SectionCard>
            {billingLoading ? (
              <View className="py-5 items-center">
                <ActivityIndicator size="small" color="#6366f1" />
              </View>
            ) : (
              <>
                <SettingsRow
                  icon="card"
                  label="Plan"
                  value={billing?.plan ?? billing?.status ?? "—"}
                />
                {billing?.renewal_date && (
                  <>
                    <Divider />
                    <SettingsRow
                      icon="calendar"
                      label="Renews"
                      value={new Date(billing.renewal_date).toLocaleDateString()}
                    />
                  </>
                )}
                {billing?.survival_mode && (
                  <>
                    <Divider />
                    <View className="px-4 py-3 flex-row items-center gap-2">
                      <Ionicons name="warning" size={16} color="#f59e0b" />
                      <Text className="text-amber-400 text-sm">Survival mode active</Text>
                    </View>
                  </>
                )}
              </>
            )}
          </SectionCard>
        </View>

        {/* Sign out */}
        <View className="px-5">
          <SectionCard>
            <SettingsRow
              icon="log-out"
              label="Sign out"
              onPress={confirmSignOut}
              destructive
            />
          </SectionCard>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
